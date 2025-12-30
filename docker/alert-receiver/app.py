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
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse, Response
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
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")  # Socket Mode용
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")  # Socket Mode에서 메시지 전송용 (선택사항)
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "C0A4LAEF6P8")  # 기본 Slack 채널

# Slack 관련 모듈 import (환경 변수 설정 후)
import slack_sender
import slack_interactions
from slack_sender import create_incident_card, send_incident_card, send_thread_reply
from slack_interactions import verify_slack_signature, parse_interaction_payload, extract_button_action
from incident_service import acknowledge_incident, resolve_incident, get_incident_info
from grafana_silence import mute_incident_via_grafana

# 모듈 변수 설정
slack_sender.SLACK_WEBHOOK_URL = SLACK_WEBHOOK_URL
slack_sender.SLACK_BOT_TOKEN = SLACK_BOT_TOKEN
slack_interactions.SLACK_SIGNING_SECRET = SLACK_SIGNING_SECRET


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


def send_to_slack(alert_info: Dict[str, Any], incident_id: str, incident_key: str, 
                  alert_count: int, is_new_incident: bool, start_time: datetime, 
                  incident_info: Optional[Dict[str, Any]] = None,
                  existing_slack_ts: Optional[str] = None) -> Optional[str]:
    """
    Slack으로 Incident 카드 전송 (Block Kit)
    
    Args:
        incident_info: Incident 정보 (이미 조회한 경우 전달, 없으면 새로 조회)
        existing_slack_ts: 기존 Incident의 경우 기존 메시지의 ts (신규일 때만 새 메시지 전송)
    
    Returns: Slack 메시지 timestamp (thread_ts) 또는 None
    """
    # SLACK_WEBHOOK_URL 또는 SLACK_BOT_TOKEN 중 하나는 있어야 함
    if not SLACK_WEBHOOK_URL and not SLACK_BOT_TOKEN:
        print("⚠️  SLACK_WEBHOOK_URL 또는 SLACK_BOT_TOKEN이 설정되지 않았습니다. Slack 전송을 건너뜁니다.")
        return None
    
    # Incident 정보 조회 (없으면 새로 조회)
    conn = None
    if not incident_info:
        conn = get_db_connection()
        try:
            incident_info = get_incident_info(conn, incident_id)
            if not incident_info:
                print(f"⚠️  Incident 정보를 찾을 수 없습니다: {incident_id}")
                if conn:
                    conn.close()
                return None
        finally:
            if conn:
                conn.close()
    
    # 기존 Incident의 경우 새 메시지를 보내지 않고 기존 메시지의 ts 사용
    if not is_new_incident and existing_slack_ts:
        print(f"🔄 기존 Incident이므로 새 메시지 전송 건너뜀, 기존 ts 사용: {existing_slack_ts}")
        ts = existing_slack_ts
    else:
        # 신규 Incident인 경우에만 새 메시지 전송
        # Block Kit 카드 생성
        blocks = create_incident_card(
            incident_id=incident_id,
            incident_key=incident_key,
            status=incident_info["status"],
            severity=alert_info["severity"],
            cluster=alert_info["cluster"] or "",
            namespace=alert_info["namespace"] or "",
            phase=alert_info["phase"] or "",
            service=alert_info["service"] or "",
            alert_count=alert_count,
            start_time=start_time,
            is_new_incident=is_new_incident
        )
        
        # Slack 전송
        ts = send_incident_card(blocks)
        print(f"📤 신규 Incident 메시지 전송: ts={ts}")
    
    # AI 분석은 버튼 클릭 시에만 실행 (자동 실행 제거)
    
    return ts


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
                # Incident 정보 조회 (start_time 등)
                incident_info = get_incident_info(conn, incident_id)
                start_time = incident_info["start_time"] if incident_info else datetime.now()
                
                # 기존 Incident의 경우 기존 메시지의 ts 조회
                existing_slack_ts = None
                if not is_new_incident:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "SELECT slack_message_ts FROM incidents WHERE incident_id = %s",
                            (incident_id,)
                        )
                        result = cursor.fetchone()
                        existing_slack_ts = result.get("slack_message_ts") if result else None
                
                slack_ts = send_to_slack(
                    alert_info, 
                    incident_id, 
                    incident_key,
                    alert_count, 
                    is_new_incident,
                    start_time,
                    incident_info=incident_info,  # 이미 조회한 정보 전달
                    existing_slack_ts=existing_slack_ts  # 기존 메시지의 ts
                )
                print(f"📤 Slack 전송: ts={slack_ts}")
                
                # 신규 Incident인 경우 slack_message_ts 저장
                if is_new_incident and slack_ts:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE incidents SET slack_message_ts = %s WHERE incident_id = %s",
                            (slack_ts, incident_id)
                        )
                    print(f"💾 Slack message_ts 저장: incident_id={incident_id}, ts={slack_ts}")
                
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


@app.post("/slack/interactions")
async def slack_interactions(
    request: Request,
    x_slack_signature: str = Header(None, alias="X-Slack-Signature"),
    x_slack_request_timestamp: str = Header(None, alias="X-Slack-Request-Timestamp")
):
    """
    Slack 인터랙션 처리 (버튼 클릭 등)
    """
    try:
        # 요청 본문 읽기
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')
        
        # 서명 검증
        if x_slack_signature and x_slack_request_timestamp:
            if not verify_slack_signature(x_slack_signature, x_slack_request_timestamp, body_str, SLACK_SIGNING_SECRET):
                print("❌ Slack 서명 검증 실패")
                return Response(status_code=401, content="Invalid signature")
        
        # Payload 파싱
        payload = parse_interaction_payload(body_str)
        if not payload:
            return Response(status_code=400, content="Invalid payload")
        
        # 버튼 액션 추출
        action_info = extract_button_action(payload)
        if not action_info:
            return Response(status_code=400, content="No action found")
        
        action_id = action_info["action_id"]
        value = action_info["value"]
        user = action_info["user"]
        message_ts = action_info.get("message_ts")
        channel = action_info.get("channel")
        
        incident_id = value.get("incident_id")
        incident_key = value.get("incident_key")
        action = value.get("action")
        
        print(f"🔘 Slack 인터랙션: {action_id} - incident_id={incident_id}, user={user.get('name', 'unknown')}")
        
        # DB 연결
        conn = get_db_connection()
        success = False
        reply_text = ""
        
        try:
            conn.autocommit(False)
            
            if action == "ack":
                success = acknowledge_incident(conn, incident_id, user.get("name", user.get("id", "unknown")))
                if success:
                    reply_text = f"👀 *Incident ACK 처리됨*\n- by @{user.get('name', 'unknown')}\n- at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    reply_text = f"❌ *Incident ACK 실패*\n- incident_id: {incident_id}\n- by @{user.get('name', 'unknown')}"
            
            elif action == "resolve":
                success = resolve_incident(conn, incident_id, user.get("name", user.get("id", "unknown")))
                if success:
                    reply_text = f"✅ *Incident RESOLVED*\n- by @{user.get('name', 'unknown')}\n- at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                else:
                    reply_text = f"❌ *Incident Resolve 실패*\n- incident_id: {incident_id}\n- by @{user.get('name', 'unknown')}"
            
            elif action.startswith("mute_"):
                # mute_30m, mute_2h, mute_24h
                # Mute는 DB 작업이 아니므로 트랜잭션 밖에서 처리
                duration_map = {
                    "mute_30m": 30,
                    "mute_2h": 120,
                    "mute_24h": 1440
                }
                duration_minutes = duration_map.get(action, 30)
                duration_text = {
                    "mute_30m": "30분",
                    "mute_2h": "2시간",
                    "mute_24h": "24시간"
                }.get(action, "30분")
                
                # Incident 정보 조회 (alertname, cluster, namespace 등)
                incident_info = get_incident_info(conn, incident_id)
                if not incident_info:
                    conn.close()
                    return Response(status_code=404, content="Incident not found")
                
                # 최근 알람에서 alertname 추출
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT alertname, labels
                        FROM grafana_alerts
                        WHERE incident_id = %s
                        ORDER BY received_at DESC
                        LIMIT 1
                    """, (incident_id,))
                    alert = cursor.fetchone()
                
                conn.close()  # Mute는 DB 작업이 아니므로 연결 종료
                
                if not alert:
                    return Response(status_code=404, content="Alert not found")
                
                # Labels에서 정보 추출
                labels = alert.get("labels") or {}
                if isinstance(labels, str):
                    import json
                    labels = json.loads(labels)
                
                alertname = alert.get("alertname") or labels.get("alertname", "")
                cluster = labels.get("cluster") or incident_info.get("cluster")
                namespace = labels.get("namespace") or incident_info.get("namespace")
                phase = labels.get("phase") or incident_info.get("phase")
                service = labels.get("service") or incident_info.get("service")
                
                # Grafana Silence 생성
                success = mute_incident_via_grafana(
                    alertname=alertname,
                    cluster=cluster,
                    namespace=namespace,
                    phase=phase,
                    service=service,
                    duration_minutes=duration_minutes,
                    user=user.get("name", user.get("id", "unknown"))
                )
                
                if success:
                    reply_text = f"🔕 *Grafana Silence 생성됨*\n- duration: {duration_text}\n- by @{user.get('name', 'unknown')}"
                else:
                    reply_text = f"❌ *Grafana Silence 생성 실패*\n- duration: {duration_text}\n- by @{user.get('name', 'unknown')}"
                
                # Slack 스레드에 댓글 추가
                if message_ts and reply_text:
                    send_thread_reply(message_ts, reply_text, channel)
                
                return Response(status_code=200, content="OK")
            
            else:
                return Response(status_code=400, content=f"Unknown action: {action}")
            
            # DB 작업 (ack, resolve)만 commit
            if success:
                conn.commit()
            else:
                conn.rollback()
                # 실패해도 Slack에 에러 메시지 전송
                if not reply_text:
                    reply_text = f"❌ *처리 실패*\n- action: {action}\n- incident_id: {incident_id}"
        
        except Exception as e:
            conn.rollback()
            print(f"❌ 인터랙션 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            return Response(status_code=500, content=str(e))
        finally:
            conn.close()
        
        # Slack 스레드에 댓글 추가 (ack, resolve)
        if message_ts and reply_text:
            send_thread_reply(message_ts, reply_text, channel)
        
        return Response(status_code=200, content="OK")
        
        # Slack에 즉시 응답 (3초 이내)
        return JSONResponse(content={
            "response_type": "ephemeral",
            "text": "처리되었습니다."
        })
    
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return Response(status_code=500, content=str(e))


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Grafana Alert Receiver",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook/grafana",
            "slack_interactions": "/slack/interactions",
            "health": "/health"
        }
    }


# Socket Mode 클라이언트 초기화 (선택사항)
socket_mode_client = None
if SLACK_APP_TOKEN:
    try:
        from slack_socket import start_socket_mode_client
        socket_mode_client = start_socket_mode_client(SLACK_APP_TOKEN, SLACK_BOT_TOKEN)
    except Exception as e:
        print(f"⚠️  Socket Mode 초기화 실패 (HTTP 방식으로 계속 작동): {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

