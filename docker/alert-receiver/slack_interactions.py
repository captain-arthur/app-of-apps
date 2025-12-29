"""
Slack 인터랙션 처리 (버튼 클릭 등)
"""
import json
import hmac
import hashlib
import time
from typing import Dict, Any, Optional
from urllib.parse import parse_qs

SLACK_SIGNING_SECRET = None  # 환경 변수에서 설정


def verify_slack_signature(signature: str, timestamp: str, body: str, signing_secret: str) -> bool:
    """
    Slack 서명 검증
    
    Args:
        signature: X-Slack-Signature 헤더 값
        timestamp: X-Slack-Request-Timestamp 헤더 값
        body: 요청 본문 (raw bytes)
        signing_secret: Slack Signing Secret
    
    Returns: 검증 성공 여부
    """
    if not signing_secret:
        print("⚠️  SLACK_SIGNING_SECRET이 설정되지 않았습니다. 서명 검증을 건너뜁니다.")
        return True  # 개발 환경에서는 검증 건너뛰기
    
    # 타임스탬프 검증 (5분 이내)
    try:
        req_timestamp = int(timestamp)
        current_timestamp = int(time.time())
        if abs(current_timestamp - req_timestamp) > 300:
            print(f"❌ 타임스탬프 만료: {current_timestamp - req_timestamp}초 차이")
            return False
    except ValueError:
        return False
    
    # 서명 생성
    sig_basestring = f"v0:{timestamp}:{body}"
    my_signature = 'v0=' + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # 서명 비교 (타이밍 공격 방지)
    return hmac.compare_digest(my_signature, signature)


def parse_interaction_payload(body: str) -> Optional[Dict[str, Any]]:
    """
    Slack 인터랙션 payload 파싱
    
    Args:
        body: 요청 본문 (URL-encoded)
    
    Returns: 파싱된 payload dict 또는 None
    """
    try:
        # URL-encoded form data 파싱
        parsed = parse_qs(body)
        if 'payload' not in parsed:
            return None
        
        payload_str = parsed['payload'][0]
        payload = json.loads(payload_str)
        return payload
    except Exception as e:
        print(f"❌ Payload 파싱 실패: {e}")
        return None


def extract_button_action(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    버튼 액션 정보 추출
    
    Returns: {
        "action_id": "incident_ack",
        "value": {"incident_id": "...", "incident_key": "...", "action": "ack"},
        "user": {"id": "...", "name": "..."}
    } 또는 None
    """
    if payload.get("type") != "block_actions":
        return None
    
    actions = payload.get("actions", [])
    if not actions:
        return None
    
    action = actions[0]  # 첫 번째 액션만 처리
    action_id = action.get("action_id")
    value_str = action.get("value")
    
    if not action_id or not value_str:
        return None
    
    try:
        value = json.loads(value_str)
    except:
        return None
    
    user = payload.get("user", {})
    
    return {
        "action_id": action_id,
        "value": value,
        "user": user,
        "response_url": payload.get("response_url"),  # 스레드 댓글용
        "channel": payload.get("channel", {}).get("id"),
        "message_ts": payload.get("message", {}).get("ts")  # 원본 메시지 timestamp
    }

