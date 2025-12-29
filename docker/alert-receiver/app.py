"""
Grafana Alert → DB → Slack 기반 Incident 관리 프로토타입
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

import httpx
import pymysql
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Grafana Alert Receiver", version="1.0.0")

# 환경 변수
DB_HOST = os.getenv("DB_HOST", "mysql")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "observer")
DB_PASSWORD = os.getenv("DB_PASSWORD", "observer123")
DB_NAME = os.getenv("DB_NAME", "observer")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


def get_db_connection():
    """MySQL 연결 생성"""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def calculate_incident_key(labels: Dict[str, Any]) -> str:
    """
    Incident Key 계산 (사건 유형 키)
    rule_uid (없으면 alertname) | cluster | namespace | phase
    → |로 연결 → SHA256 → 앞 16자
    
    주의: service, pod, node, instance는 포함하지 않음
    (알람 폭발 방지 및 namespace 단위 운영)
    """
    rule_uid = labels.get("rule_uid", labels.get("alertname", "unknown"))
    cluster = labels.get("cluster", "default")
    namespace = labels.get("namespace", "default")
    phase = labels.get("phase", labels.get("environment", "default"))
    
    fingerprint_str = f"{rule_uid}|{cluster}|{namespace}|{phase}"
    incident_key = hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]
    return incident_key


def generate_incident_id() -> str:
    """
    Incident ID 생성 (에피소드 ID, 매번 새로 생성)
    형식: INC-YYYYMMDDHHMMSS-{random_hex}
    이번에 대응한 사건(episode)의 고유 ID
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_suffix = hashlib.sha256(f"{timestamp}{os.urandom(16)}".encode()).hexdigest()[:8]
    return f"INC-{timestamp}-{random_suffix}"


def extract_alert_info(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Grafana alert에서 정보 추출"""
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    
    return {
        "rule_uid": labels.get("rule_uid", ""),
        "alertname": labels.get("alertname", labels.get("__alert_rule_title__", "Unknown")),
        "state": alert.get("status", "firing"),
        "severity": labels.get("severity", "warning"),
        "cluster": labels.get("cluster", ""),
        "namespace": labels.get("namespace", ""),
        "service": labels.get("service", labels.get("job", "")),
        "service_category": labels.get("service_category", labels.get("category", "")),  # 서비스 대분류
        "phase": labels.get("phase", labels.get("environment", "")),
        "message": annotations.get("description", annotations.get("summary", "")),
        "labels": labels,
        "annotations": annotations,
    }


def save_alert_to_db(conn, alert_info: Dict[str, Any], raw_payload: Dict[str, Any], incident_id: str, incident_key: str) -> int:
    """
    알람을 grafana_alerts 테이블에 저장 (incident_id, incident_key 포함)
    주의: commit은 호출자에서 처리 (트랜잭션 범위 확대)
    """
    with conn.cursor() as cursor:
        sql = """
        INSERT INTO grafana_alerts 
        (incident_id, incident_key, received_at, state, rule_uid, alertname, message, labels, annotations, raw_payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (
            incident_id,
            incident_key,
            datetime.now(),
            alert_info["state"],
            alert_info["rule_uid"],
            alert_info["alertname"],
            alert_info["message"],
            json.dumps(alert_info["labels"]),
            json.dumps(alert_info["annotations"]),
            json.dumps(raw_payload)
        ))
        # commit 제거: 호출자에서 처리
        return cursor.lastrowid


def find_or_create_incident(conn, incident_key: str, alert_info: Dict[str, Any]) -> tuple[str, bool]:
    """
    Open Incident 찾기 또는 새로 생성
    - open incident 조회 (status IN ('active','acknowledged'))
    - SELECT FOR UPDATE로 Row Lock하여 동시성 문제 해결
    - 있으면 기존 사용 (업데이트: last_seen_at, severity)
    - 없으면 새로 생성
    - 주의: commit은 호출자에서 처리 (트랜잭션 범위 확대)
    
    Returns: (incident_id, is_new_incident)
    """
    with conn.cursor() as cursor:
        # Open incident 조회 (SELECT FOR UPDATE로 Row Lock)
        # 동시성 문제 해결: 같은 incident_key로 동시 요청 시 하나만 처리
        cursor.execute("""
            SELECT incident_id, alert_count 
            FROM incidents 
            WHERE incident_key = %s 
              AND status IN ('active', 'acknowledged')
            ORDER BY last_seen_at DESC
            LIMIT 1
            FOR UPDATE  -- Row Lock: 동시성 문제 해결
        """, (incident_key,))
        existing = cursor.fetchone()
        
        if existing:
            # 기존 open incident 사용
            incident_id = existing["incident_id"]
            # 업데이트: last_seen_at 갱신, severity 업데이트, status를 active로 변경
            # alert_count는 트리거가 자동으로 업데이트하므로 수동 증가 제거
            cursor.execute("""
                UPDATE incidents 
                SET last_seen_at = %s,
                    severity = %s,
                    status = 'active',
                    updated_at = %s
                WHERE incident_id = %s
            """, (
                datetime.now(),
                alert_info["severity"],
                datetime.now(),
                incident_id
            ))
            # commit 제거: 호출자에서 처리
            return (incident_id, False)  # 기존 incident
        else:
            # 신규 생성
            # 트리거가 중복 체크를 하지만, 애플리케이션 레벨에서도 한번 더 확인
            incident_id = generate_incident_id()
            now = datetime.now()
            cursor.execute("""
                INSERT INTO incidents 
                (incident_id, incident_key, status, severity, phase, cluster, namespace, service, 
                 service_category, start_time, first_seen_at, last_seen_at, alert_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                incident_id,
                incident_key,
                "active",
                alert_info["severity"],
                alert_info["phase"],
                alert_info["cluster"],
                alert_info["namespace"],
                alert_info["service"],
                alert_info.get("service_category"),  # 서비스 대분류 (labels에서 추출)
                now,  # start_time
                now,  # first_seen_at
                now,  # last_seen_at
                0  # 초기값 0, 트리거가 자동으로 업데이트
            ))
            # commit 제거: 호출자에서 처리
            return (incident_id, True)  # 신규 incident


# check_silence 함수 제거 (이번 단순화 범위에서 제외)
# link_alert_to_incident 함수 제거 (grafana_alerts.incident_id FK로 직접 연결)


def send_to_slack(alert_info: Dict[str, Any], incident_id: str, alert_count: int, is_new_incident: bool):
    """Slack으로 알람 전송"""
    if not SLACK_WEBHOOK_URL:
        print("⚠️  SLACK_WEBHOOK_URL이 설정되지 않았습니다. Slack 전송을 건너뜁니다.")
        return
    
    severity_emoji = {
        "critical": "🚨",
        "warning": "⚠️",
        "info": "ℹ️"
    }.get(alert_info["severity"].lower(), "📢")
    
    status_text = "🆕 신규 사건" if is_new_incident else "🔄 기존 사건"
    
    message = f"""{severity_emoji} [{alert_info['severity'].upper()}] {alert_info['alertname']}

{status_text}
Incident ID: `{incident_id}`
Alerts linked: {alert_count}

**상세 정보:**
• Cluster: {alert_info['cluster'] or 'N/A'}
• Namespace: {alert_info['namespace'] or 'N/A'}
• Service: {alert_info['service'] or 'N/A'}
• Phase: {alert_info['phase'] or 'N/A'}

**메시지:**
{alert_info['message'] or 'No description'}
"""
    
    try:
        response = httpx.post(
            SLACK_WEBHOOK_URL,
            json={"text": message},
            timeout=5.0
        )
        response.raise_for_status()
        print(f"✅ Slack 전송 성공: {incident_id}")
    except Exception as e:
        print(f"❌ Slack 전송 실패: {e}")


@app.post("/webhook/grafana")
async def grafana_webhook(request: Request):
    """
    Grafana Webhook 수신 엔드포인트
    Grafana Alert Rule에서 이 엔드포인트를 호출하도록 설정
    """
    try:
        payload = await request.json()
        # 전체 페이로드를 여러 줄로 출력하여 잘림 방지
        payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
        print(f"📥 Grafana webhook 수신 (전체 길이: {len(payload_str)} 문자)")
        print("=" * 80)
        # 각 줄을 개별적으로 출력하여 Docker 로그 버퍼 제한 회피
        # sys.stdout을 직접 사용하여 버퍼링 방지
        import sys
        sys.stdout.write(payload_str)
        sys.stdout.write("\n")
        sys.stdout.flush()
        print("=" * 80)
        
        # Grafana webhook 형식 처리
        alerts = payload.get("alerts", [])
        if not alerts:
            return JSONResponse(
                status_code=400,
                content={"error": "No alerts in payload"}
            )
        
        conn = get_db_connection()
        results = []
        
        try:
            # 트랜잭션 시작 (autocommit=False로 시작)
            conn.autocommit(False)
            
            for alert in alerts:
                # 1. Alert 정보 추출
                alert_info = extract_alert_info(alert)
                
                # 2. Incident Key 계산 (사건 유형 키)
                # rule_uid | cluster | namespace | phase (service, pod, node 제외)
                incident_key = calculate_incident_key(alert_info["labels"])
                print(f"🔑 Incident Key 계산: {incident_key}")
                
                # 3. Open Incident 찾기 또는 새로 생성
                # SELECT FOR UPDATE로 Row Lock하여 동시성 문제 해결
                incident_id, is_new_incident = find_or_create_incident(conn, incident_key, alert_info)
                print(f"{'🆕 신규' if is_new_incident else '🔄 기존'} Incident: {incident_id} (key: {incident_key})")
                
                # 4. grafana_alerts에 원본 저장 (incident_id, incident_key 포함)
                # 트리거가 alert_count를 자동으로 업데이트
                alert_id = save_alert_to_db(conn, alert_info, alert, incident_id, incident_key)
                print(f"✅ Alert 저장됨: alert_id={alert_id} → incident_id={incident_id}")
                
                # 5. Incident 정보 조회 (alert_count 등)
                # 트리거가 업데이트한 alert_count 조회
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT alert_count FROM incidents WHERE incident_id = %s",
                        (incident_id,)
                    )
                    incident = cursor.fetchone()
                    alert_count = incident["alert_count"] if incident else 1
                
                # 6. Slack 전송
                send_to_slack(alert_info, incident_id, alert_count, is_new_incident)
                
                results.append({
                    "alert_id": alert_id,
                    "incident_id": incident_id,
                    "incident_key": incident_key,
                    "is_new_incident": is_new_incident,
                    "alert_count": alert_count
                })
            
            # 전체 트랜잭션 커밋 (모든 alert 처리 완료 후)
            conn.commit()
            print(f"✅ 트랜잭션 커밋 완료: {len(results)}개 alert 처리")
        
        except Exception as e:
            # 에러 발생 시 롤백
            conn.rollback()
            print(f"❌ 트랜잭션 롤백: {e}")
            raise
        finally:
            conn.close()
        
        return JSONResponse(content={
            "status": "success",
            "processed": len(results),
            "results": results
        })
    
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check 엔드포인트"""
    try:
        conn = get_db_connection()
        conn.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Grafana Alert Receiver",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook/grafana",
            "health": "/health"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

