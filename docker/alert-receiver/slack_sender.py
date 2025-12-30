"""
Slack Block Kit 메시지 생성 및 전송
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional
import httpx
import os

SLACK_WEBHOOK_URL = None  # app.py에서 설정
SLACK_BOT_TOKEN = None  # app.py에서 설정
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "C0A4LAEF6P8")  # 기본 채널 ID


def create_incident_card(incident_id: str, incident_key: str, status: str, severity: str,
                         cluster: str, namespace: str, phase: str, service: str,
                         alert_count: int, start_time: datetime, is_new_incident: bool) -> Dict[str, Any]:
    """
    Incident Block Kit 카드 생성
    
    Returns: Slack Block Kit JSON
    """
    severity_emoji = {
        "critical": "🚨",
        "warning": "⚠️",
        "info": "ℹ️"
    }.get(severity.lower(), "📢")
    
    status_text = {
        "active": "🟢 Active",
        "acknowledged": "🟡 Acknowledged",
        "resolved": "🔵 Resolved"
    }.get(status, "❓ Unknown")
    
    # 버튼 value JSON
    button_value = json.dumps({
        "incident_id": incident_id,
        "incident_key": incident_key,
        "action": ""  # 각 버튼에서 채움
    })
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_emoji} Incident 발생",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Incident ID:*\n`{incident_id}`"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Status:*\n{status_text}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Severity:*\n{severity.upper()}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Alerts:*\n{alert_count}"
                }
            ]
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Cluster:*\n{cluster or 'N/A'}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Namespace:*\n{namespace or 'N/A'}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Phase:*\n{phase or 'N/A'}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Service:*\n{service or 'N/A'}"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"발생 시각: {start_time.strftime('%Y-%m-%d %H:%M:%S')} | Signature: `{incident_key}`"
                }
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "👀 Ack",
                        "emoji": True
                    },
                    "style": "primary",
                    "action_id": "incident_ack",
                    "value": json.dumps({
                        "incident_id": incident_id,
                        "incident_key": incident_key,
                        "action": "ack"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Resolve",
                        "emoji": True
                    },
                    "style": "danger",
                    "action_id": "incident_resolve",
                    "value": json.dumps({
                        "incident_id": incident_id,
                        "incident_key": incident_key,
                        "action": "resolve"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🤖 AI 분석",
                        "emoji": True
                    },
                    "action_id": "incident_ai_analysis",
                    "value": json.dumps({
                        "incident_id": incident_id,
                        "incident_key": incident_key,
                        "action": "ai_analysis"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🔕 Mute 30m",
                        "emoji": True
                    },
                    "action_id": "incident_mute_30m",
                    "value": json.dumps({
                        "incident_id": incident_id,
                        "incident_key": incident_key,
                        "action": "mute_30m"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🔕 Mute 2h",
                        "emoji": True
                    },
                    "action_id": "incident_mute_2h",
                    "value": json.dumps({
                        "incident_id": incident_id,
                        "incident_key": incident_key,
                        "action": "mute_2h"
                    })
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "🔕 Mute 24h",
                        "emoji": True
                    },
                    "action_id": "incident_mute_24h",
                    "value": json.dumps({
                        "incident_id": incident_id,
                        "incident_key": incident_key,
                        "action": "mute_24h"
                    })
                }
            ]
        }
    ]
    
    return {
        "blocks": blocks
    }


def send_incident_card(blocks: Dict[str, Any], channel: str = None) -> Optional[str]:
    """
    Slack에 Incident 카드 전송
    
    Returns: Slack 메시지 timestamp (thread_ts로 사용)
    """
    # 채널 ID 설정 (기본값 사용)
    target_channel = channel or SLACK_CHANNEL
    
    # SLACK_WEBHOOK_URL이 있으면 Webhook 사용, 없으면 SLACK_BOT_TOKEN으로 WebClient 사용
    if SLACK_WEBHOOK_URL:
        payload = {
            "blocks": blocks["blocks"]
        }
        
        if target_channel:
            payload["channel"] = target_channel
        
        try:
            response = httpx.post(
                SLACK_WEBHOOK_URL,
                json=payload,
                timeout=5.0
            )
            response.raise_for_status()
            # Slack Incoming Webhook은 성공 시 "ok" 문자열 또는 빈 응답을 반환할 수 있음
            try:
                result = response.json()
                ts = result.get("ts") if isinstance(result, dict) else None
            except:
                text = response.text.strip()
                if text == "ok" or not text:
                    ts = None
                else:
                    ts = None
            print(f"✅ Slack Incident 카드 전송 성공 (Webhook)")
            return ts
        except Exception as e:
            print(f"❌ Slack 전송 실패 (Webhook): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    elif SLACK_BOT_TOKEN:
        # WebClient 사용 (Socket Mode)
        try:
            from slack_sdk import WebClient
            web_client = WebClient(token=SLACK_BOT_TOKEN)
            
            result = web_client.chat_postMessage(
                channel=target_channel,
                blocks=blocks["blocks"]
            )
            
            ts = result.get("ts") if result else None
            print(f"✅ Slack Incident 카드 전송 성공 (WebClient): ts={ts}")
            return ts
        except Exception as e:
            print(f"❌ Slack 전송 실패 (WebClient): {e}")
            import traceback
            traceback.print_exc()
            return None
    else:
        print("⚠️  SLACK_WEBHOOK_URL 또는 SLACK_BOT_TOKEN이 설정되지 않았습니다. Slack 전송을 건너뜁니다.")
        return None


def send_thread_reply(thread_ts: str, text: str, channel: str = None, webhook_url: str = None) -> bool:
    """
    Slack 스레드에 댓글 추가
    
    Args:
        thread_ts: 원본 메시지의 timestamp
        text: 댓글 텍스트
        channel: 채널 ID (선택)
        webhook_url: Slack Webhook URL (없으면 전역 변수 사용)
    
    Returns: 성공 여부
    """
    # 전역 변수 또는 파라미터에서 webhook_url 가져오기
    import slack_sender as slack_sender_module
    url = webhook_url or getattr(slack_sender_module, 'SLACK_WEBHOOK_URL', None)
    
    if not url:
        return False
    
    payload = {
        "text": text,
        "thread_ts": thread_ts
    }
    
    if channel:
        payload["channel"] = channel
    
    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=5.0
        )
        response.raise_for_status()
        print(f"✅ Slack 스레드 댓글 전송 성공: {thread_ts}")
        return True
    except Exception as e:
        print(f"❌ Slack 스레드 댓글 전송 실패: {e}")
        return False

