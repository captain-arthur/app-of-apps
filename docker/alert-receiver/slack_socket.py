"""
Slack Socket Mode 클라이언트
Socket Mode를 사용하여 Interactive Components 처리
"""
import json
import os
from typing import Dict, Any, Optional
from slack_sdk import WebClient
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

# 전역 변수 (app.py에서 설정)
SLACK_APP_TOKEN = None
SLACK_BOT_TOKEN = None  # Socket Mode에서는 필요 없지만, WebClient용으로 유지
socket_client = None

# app.py에서 import할 함수들
from incident_service import acknowledge_incident, resolve_incident, get_incident_info
from grafana_silence import mute_incident_via_grafana
from datetime import datetime
import json


def get_db_connection():
    """DB 연결"""
    import pymysql
    import os
    return pymysql.connect(
        host=os.getenv("DB_HOST", "mysql"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "observer"),
        password=os.getenv("DB_PASSWORD", "observer123"),
        database=os.getenv("DB_NAME", "observer"),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def handle_interactive_components(client: SocketModeClient, req: SocketModeRequest):
    """
    Interactive Components (버튼 클릭) 처리
    """
    print(f"📥 Socket Mode 요청 수신: type={req.type}, envelope_id={req.envelope_id}")
    
    # Acknowledge the request
    response = SocketModeResponse(envelope_id=req.envelope_id)
    client.send_socket_mode_response(response)
    
    # Parse payload
    payload = req.payload
    print(f"📦 Payload type: {payload.get('type')}")
    
    if payload.get("type") != "block_actions":
        print(f"⚠️  block_actions가 아님: {payload.get('type')}")
        return
    
    actions = payload.get("actions", [])
    if not actions:
        print("⚠️  actions가 없음")
        return
    
    action = actions[0]
    action_id = action.get("action_id")
    value_str = action.get("value")
    
    print(f"🔍 Action ID: {action_id}, Value: {value_str}")
    
    if not action_id or not value_str:
        print("⚠️  action_id 또는 value가 없음")
        return
    
    try:
        value = json.loads(value_str)
    except Exception as e:
        print(f"❌ JSON 파싱 실패: {e}")
        return
    
    incident_id = value.get("incident_id")
    incident_key = value.get("incident_key")
    action_type = value.get("action")
    user = payload.get("user", {})
    channel = payload.get("channel", {}).get("id")
    message_ts = payload.get("message", {}).get("ts")
    
    print(f"🔘 Slack 인터랙션 (Socket Mode): {action_id} - incident_id={incident_id}, user={user.get('name', 'unknown')}")
    
    # DB 연결
    conn = get_db_connection()
    success = False
    reply_text = ""
    
    try:
        conn.autocommit(False)
        
        if action_type == "ack":
            success = acknowledge_incident(conn, incident_id, user.get("name", user.get("id", "unknown")))
            if success:
                reply_text = f"👀 *Incident ACK 처리됨*\n- by @{user.get('name', 'unknown')}\n- at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                reply_text = f"❌ *Incident ACK 실패*\n- incident_id: {incident_id}\n- by @{user.get('name', 'unknown')}"
        
        elif action_type == "resolve":
            success = resolve_incident(conn, incident_id, user.get("name", user.get("id", "unknown")))
            if success:
                reply_text = f"✅ *Incident RESOLVED*\n- by @{user.get('name', 'unknown')}\n- at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                reply_text = f"❌ *Incident Resolve 실패*\n- incident_id: {incident_id}\n- by @{user.get('name', 'unknown')}"
        
        elif action_type.startswith("mute_"):
            # mute_30m, mute_2h, mute_24h
            # Mute는 DB 작업이 아니므로 트랜잭션 밖에서 처리
            duration_map = {
                "mute_30m": 30,
                "mute_2h": 120,
                "mute_24h": 1440
            }
            duration_minutes = duration_map.get(action_type, 30)
            duration_text = {
                "mute_30m": "30분",
                "mute_2h": "2시간",
                "mute_24h": "24시간"
            }.get(action_type, "30분")
            
            # Incident 정보 조회
            incident_info = get_incident_info(conn, incident_id)
            if not incident_info:
                conn.close()
                return
            
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
                return
            
            # Labels에서 정보 추출
            labels = alert.get("labels") or {}
            if isinstance(labels, str):
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
            if message_ts and reply_text and channel:
                try:
                    import slack_sender
                    webhook_url = getattr(slack_sender, 'SLACK_WEBHOOK_URL', None)
                    
                    if webhook_url:
                        from slack_sender import send_thread_reply
                        send_thread_reply(message_ts, reply_text, channel)
                    elif SLACK_BOT_TOKEN:
                        web_client = WebClient(token=SLACK_BOT_TOKEN)
                        web_client.chat_postMessage(
                            channel=channel,
                            thread_ts=message_ts,
                            text=reply_text
                        )
                        print(f"✅ Slack 스레드 댓글 전송 성공 (Socket Mode): {message_ts}")
                except Exception as e:
                    print(f"❌ Slack 스레드 댓글 전송 실패: {e}")
            
            return  # Mute는 DB 작업이 아니므로 여기서 종료
        
        # DB 작업 (ack, resolve)만 commit
        if success:
            conn.commit()
        else:
            conn.rollback()
            # 실패해도 Slack에 에러 메시지 전송
            if not reply_text:
                reply_text = f"❌ *처리 실패*\n- action: {action_type}\n- incident_id: {incident_id}"
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ 인터랙션 처리 실패: {e}")
        import traceback
        traceback.print_exc()
        # 예외 발생 시에도 에러 메시지 설정
        if not reply_text:
            reply_text = f"❌ *처리 중 오류 발생*\n- action: {action_type}\n- error: {str(e)}"
    finally:
        if conn:
            conn.close()
    
    # Slack 스레드에 댓글 추가
    if message_ts and reply_text and channel:
        try:
            # Socket Mode에서는 WebClient를 사용하여 메시지 전송
            # SLACK_WEBHOOK_URL이 있으면 webhook 사용, 없으면 WebClient 사용
            import slack_sender
            webhook_url = getattr(slack_sender, 'SLACK_WEBHOOK_URL', None)
            
            if webhook_url:
                # Webhook 사용 (기존 방식)
                from slack_sender import send_thread_reply
                send_thread_reply(message_ts, reply_text, channel)
            elif SLACK_BOT_TOKEN:
                # WebClient 사용 (Socket Mode)
                web_client = WebClient(token=SLACK_BOT_TOKEN)
                web_client.chat_postMessage(
                    channel=channel,
                    thread_ts=message_ts,
                    text=reply_text
                )
                print(f"✅ Slack 스레드 댓글 전송 성공 (Socket Mode): {message_ts}")
            else:
                print("⚠️  SLACK_BOT_TOKEN 또는 SLACK_WEBHOOK_URL이 설정되지 않아 스레드 댓글을 전송할 수 없습니다.")
        except Exception as e:
            print(f"❌ Slack 스레드 댓글 전송 실패: {e}")
            import traceback
            traceback.print_exc()


def start_socket_mode_client(app_token: str, bot_token: str = None):
    """
    Socket Mode 클라이언트 시작
    
    Args:
        app_token: App-Level Token (xapp-1-xxxxx)
        bot_token: Bot User OAuth Token (선택사항, 메시지 전송용)
    """
    global socket_client, SLACK_APP_TOKEN, SLACK_BOT_TOKEN
    
    SLACK_APP_TOKEN = app_token
    SLACK_BOT_TOKEN = bot_token
    
    if not app_token:
        print("⚠️  SLACK_APP_TOKEN이 설정되지 않았습니다. Socket Mode를 시작할 수 없습니다.")
        return None
    
    try:
        # Initialize Socket Mode client
        socket_client = SocketModeClient(
            app_token=app_token,
            web_client=WebClient(token=bot_token) if bot_token else None
        )
        
        # Register handler
        socket_client.socket_mode_request_listeners.append(handle_interactive_components)
        
        # Start client
        socket_client.connect()
        print("✅ Slack Socket Mode 클라이언트 시작됨")
        return socket_client
    except Exception as e:
        print(f"❌ Socket Mode 클라이언트 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        return None


def stop_socket_mode_client():
    """Socket Mode 클라이언트 종료"""
    global socket_client
    if socket_client:
        socket_client.disconnect()
        print("✅ Slack Socket Mode 클라이언트 종료됨")

