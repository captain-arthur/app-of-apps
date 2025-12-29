"""
Grafana Silence API 연동
Slack Mute 버튼 클릭 시 Grafana Silence 생성
"""
import os
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://host.docker.internal:32570")
GRAFANA_USER = os.getenv("GRAFANA_USER", "admin")
GRAFANA_PASSWORD = os.getenv("GRAFANA_PASSWORD", "admin")


def create_grafana_silence(
    alertname: str,
    cluster: str = None,
    namespace: str = None,
    phase: str = None,
    service: str = None,
    duration_minutes: int = 30,
    comment: str = "Muted from Slack"
) -> Optional[str]:
    """
    Grafana Silence 생성
    
    Args:
        alertname: 알람 이름
        cluster: 클러스터
        namespace: 네임스페이스
        phase: 환경
        service: 서비스
        duration_minutes: 음소거 시간 (분)
        comment: 주석
    
    Returns: Silence ID 또는 None
    """
    try:
        # Grafana API 인증
        auth = (GRAFANA_USER, GRAFANA_PASSWORD)
        
        # Matchers 생성 (labels 기반)
        matchers = [
            {
                "name": "alertname",
                "value": alertname,
                "isRegex": False
            }
        ]
        
        if cluster:
            matchers.append({
                "name": "cluster",
                "value": cluster,
                "isRegex": False
            })
        
        if namespace:
            matchers.append({
                "name": "namespace",
                "value": namespace,
                "isRegex": False
            })
        
        if phase:
            matchers.append({
                "name": "phase",
                "value": phase,
                "isRegex": False
            })
        
        if service:
            matchers.append({
                "name": "service",
                "value": service,
                "isRegex": False
            })
        
        # 시작/종료 시간
        starts_at = datetime.now()
        ends_at = starts_at + timedelta(minutes=duration_minutes)
        
        # Grafana Silence 생성 API 호출
        # Grafana Alerting API: POST /api/alertmanager/grafana/api/v2/silences
        url = f"{GRAFANA_URL}/api/alertmanager/grafana/api/v2/silences"
        
        payload = {
            "matchers": matchers,
            "startsAt": starts_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "endsAt": ends_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "comment": comment,
            "createdBy": "Slack Bot"
        }
        
        response = httpx.post(
            url,
            json=payload,
            auth=auth,
            timeout=10.0
        )
        response.raise_for_status()
        
        result = response.json()
        silence_id = result.get("silenceID")
        
        print(f"✅ Grafana Silence 생성 성공: silence_id={silence_id}, duration={duration_minutes}분")
        return silence_id
        
    except Exception as e:
        print(f"❌ Grafana Silence 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def mute_incident_via_grafana(
    alertname: str,
    cluster: str = None,
    namespace: str = None,
    phase: str = None,
    service: str = None,
    duration_minutes: int = 30,
    user: str = "unknown"
) -> bool:
    """
    Incident를 Grafana Silence로 음소거
    
    Args:
        alertname: 알람 이름
        cluster: 클러스터
        namespace: 네임스페이스
        phase: 환경
        service: 서비스
        duration_minutes: 음소거 시간 (분)
        user: 사용자
    
    Returns: 성공 여부
    """
    comment = f"Muted from Slack by {user} for {duration_minutes} minutes"
    silence_id = create_grafana_silence(
        alertname=alertname,
        cluster=cluster,
        namespace=namespace,
        phase=phase,
        service=service,
        duration_minutes=duration_minutes,
        comment=comment
    )
    
    return silence_id is not None

