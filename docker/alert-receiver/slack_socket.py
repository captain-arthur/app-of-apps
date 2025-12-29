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


def handle_reaction_added(client: SocketModeClient, req: SocketModeRequest):
    """
    Reaction Added (이모티콘 리액션) 처리
    """
    # Acknowledge the request
    response = SocketModeResponse(envelope_id=req.envelope_id)
    client.send_socket_mode_response(response)
    
    # Parse event
    event = req.payload.get("event", {})
    if event.get("type") != "reaction_added":
        return
    
    reaction = event.get("reaction", "")
    item = event.get("item", {})
    user = event.get("user", "")
    channel = item.get("channel", "")
    message_ts = item.get("ts", "")
    
    print(f"😀 리액션 추가: {reaction} - user={user}, message_ts={message_ts}")
    
    # 이모티콘 → 액션 매핑
    reaction_to_action = {
        "eyes": "ack",  # 👀
        "white_check_mark": "resolve",  # ✅
        "no_bell": "mute_30m",  # 🔕
    }
    
    action_type = reaction_to_action.get(reaction)
    if not action_type:
        print(f"⚠️  알 수 없는 리액션: {reaction}")
        return
    
    # 메시지 조회하여 incident_id 추출
    if not SLACK_BOT_TOKEN:
        print("⚠️  SLACK_BOT_TOKEN이 없어 메시지를 조회할 수 없습니다.")
        return
    
    try:
        web_client = WebClient(token=SLACK_BOT_TOKEN)
        # 메시지 조회
        result = web_client.conversations_history(
            channel=channel,
            latest=message_ts,
            limit=1,
            inclusive=True
        )
        
        messages = result.get("messages", [])
        if not messages:
            print("⚠️  메시지를 찾을 수 없습니다.")
            return
        
        message = messages[0]
        blocks = message.get("blocks", [])
        
        # 블록에서 incident_id 추출
        incident_id = None
        incident_key = None
        
        for block in blocks:
            if block.get("type") == "section":
                fields = block.get("fields", [])
                for field in fields:
                    text = field.get("text", "")
                    if "Incident ID" in text:
                        # `INC-xxxxx` 패턴 추출
                        import re
                        match = re.search(r'INC-[A-Za-z0-9-]+', text)
                        if match:
                            incident_id = match.group(0)
                    elif "Signature" in text:
                        # `56f756c790c8fa59` 패턴 추출
                        import re
                        match = re.search(r'`([a-f0-9]+)`', text)
                        if match:
                            incident_key = match.group(1)
        
        if not incident_id:
            print("⚠️  메시지에서 incident_id를 찾을 수 없습니다.")
            return
        
        print(f"🔍 리액션 처리: {reaction} → {action_type}, incident_id={incident_id}")
        
        # 기존 버튼 처리 로직 재사용
        process_incident_action(
            action_type=action_type,
            incident_id=incident_id,
            incident_key=incident_key,
            user={"id": user, "name": user},
            channel=channel,
            message_ts=message_ts
        )
        
    except Exception as e:
        print(f"❌ 리액션 처리 실패: {e}")
        import traceback
        traceback.print_exc()


def process_incident_action(action_type: str, incident_id: str, incident_key: str,
                           user: dict, channel: str, message_ts: str):
    """
    Incident 액션 처리 (버튼과 리액션 공통 로직)
    """
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
    
    # Slack 스레드에 댓글 추가 (ack, resolve)
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


def create_resolve_modal(incident_id: str, incident_key: str, channel: str = None, message_ts: str = None) -> dict:
    """
    Resolve 모달 생성
    """
    return {
        "type": "modal",
        "title": {
            "type": "plain_text",
            "text": "Incident Resolve"
        },
        "submit": {
            "type": "plain_text",
            "text": "Resolve"
        },
        "close": {
            "type": "plain_text",
            "text": "Cancel"
        },
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Incident ID:* `{incident_id}`\n*Signature:* `{incident_key}`"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "input",
                "block_id": "action_taken",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "action_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "조치 내용을 입력하세요 (예: 서비스 재시작, 설정 변경 등)"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "조치 내용"
                },
                "optional": True
            },
            {
                "type": "input",
                "block_id": "root_cause",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "root_cause_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "근본 원인을 입력하세요"
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "근본 원인"
                },
                "optional": True
            }
        ],
        "private_metadata": json.dumps({
            "incident_id": incident_id,
            "incident_key": incident_key,
            "channel": channel,
            "message_ts": message_ts
        })
    }


def handle_view_submission(client: SocketModeClient, req: SocketModeRequest):
    """
    View Submission (모달 제출) 처리
    """
    response = SocketModeResponse(envelope_id=req.envelope_id)
    
    payload = req.payload
    view = payload.get("view", {})
    private_metadata = view.get("private_metadata", "{}")
    
    try:
        metadata = json.loads(private_metadata)
        incident_id = metadata.get("incident_id")
        incident_key = metadata.get("incident_key")
        channel = metadata.get("channel")
        message_ts = metadata.get("message_ts")
        user = payload.get("user", {})
        
        # 입력값 추출
        values = view.get("state", {}).get("values", {})
        action_taken = values.get("action_taken", {}).get("action_input", {}).get("value", "")
        root_cause = values.get("root_cause", {}).get("root_cause_input", {}).get("value", "")
        
        print(f"📝 모달 제출: incident_id={incident_id}, action_taken={action_taken[:50]}..., root_cause={root_cause[:50]}...")
        
        # DB 연결
        conn = get_db_connection()
        try:
            conn.autocommit(False)
            
            # Resolve 처리 + 입력값 저장
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE incidents 
                    SET status = 'resolved',
                        resolved_time = %s,
                        resolved_by = %s,
                        action_taken = %s,
                        root_cause = %s,
                        updated_at = %s
                    WHERE incident_id = %s
                """, (
                    datetime.now(),
                    user.get("name", user.get("id", "unknown")),
                    action_taken if action_taken else None,
                    root_cause if root_cause else None,
                    datetime.now(),
                    incident_id
                ))
            
            conn.commit()
            print(f"✅ Incident Resolve 완료: {incident_id}")
            
            # 원본 메시지 스레드에 댓글 추가
            if channel and message_ts and SLACK_BOT_TOKEN:
                try:
                    reply_text = f"✅ *Incident RESOLVED*\n- by @{user.get('name', 'unknown')}\n- at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    if action_taken:
                        reply_text += f"\n- *조치 내용:* {action_taken[:200]}"
                    if root_cause:
                        reply_text += f"\n- *근본 원인:* {root_cause[:200]}"
                    
                    web_client = WebClient(token=SLACK_BOT_TOKEN)
                    web_client.chat_postMessage(
                        channel=channel,
                        thread_ts=message_ts,
                        text=reply_text
                    )
                    print(f"✅ Slack 스레드 댓글 전송 성공: {message_ts}")
                except Exception as e:
                    print(f"❌ Slack 스레드 댓글 전송 실패: {e}")
            
            # 성공 응답
            response.response_action = "clear"
            
        except Exception as e:
            conn.rollback()
            print(f"❌ 모달 제출 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            # 에러 응답
            response.response_action = "errors"
            response.errors = {
                "action_taken": "처리 중 오류가 발생했습니다."
            }
        finally:
            conn.close()
    
    except Exception as e:
        print(f"❌ 모달 제출 파싱 실패: {e}")
        response.response_action = "errors"
        response.errors = {
            "action_taken": "요청을 처리할 수 없습니다."
        }
    
    client.send_socket_mode_response(response)


def handle_interactive_components(client: SocketModeClient, req: SocketModeRequest):
    """
    Interactive Components (버튼 클릭) 처리
    """
    print(f"📥 Socket Mode 요청 수신: type={req.type}, envelope_id={req.envelope_id}")
    
    # Parse payload
    payload = req.payload
    
    # view_submission 처리 (모달 제출)
    if payload.get("type") == "view_submission":
        handle_view_submission(client, req)
        return
    
    # reaction_added 이벤트는 별도 핸들러로
    if req.type == "events_api":
        event = payload.get("event", {})
        if event.get("type") == "reaction_added":
            handle_reaction_added(client, req)
            return
    
    print(f"📦 Payload type: {payload.get('type')}")
    
    # trigger_id는 req 객체에 있을 수도 있음
    trigger_id_from_req = getattr(req, 'trigger_id', None)
    print(f"🔍 trigger_id 확인 (req): {trigger_id_from_req}")
    print(f"🔍 trigger_id 확인 (payload): {payload.get('trigger_id')}")
    print(f"📦 Payload keys: {list(payload.keys())[:20]}")
    
    if payload.get("type") != "block_actions":
        print(f"⚠️  block_actions가 아님: {payload.get('type')}")
        # Acknowledge the request
        response = SocketModeResponse(envelope_id=req.envelope_id)
        client.send_socket_mode_response(response)
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
    print(f"🔍 action_type 확인: {action_type}, type={type(action_type)}")
    
    # Resolve 버튼 클릭 시 모달 열기 (응답 전에 처리해야 함!)
    if action_type == "resolve":
        print(f"✅ action_type이 'resolve'입니다. 모달 열기 시작...")
        
        # trigger_id는 여러 위치에 있을 수 있음
        trigger_id = (
            payload.get("trigger_id") or 
            payload.get("container", {}).get("trigger_id") or
            getattr(req, 'trigger_id', None)
        )
        print(f"🔍 모달 열기 시도: trigger_id={trigger_id}, SLACK_BOT_TOKEN={'있음' if SLACK_BOT_TOKEN else '없음'}")
        
        if not trigger_id:
            print("⚠️  trigger_id가 없습니다. payload를 확인합니다.")
            print(f"📦 Payload keys: {list(payload.keys())}")
            print(f"📦 Payload 전체 (처음 2000자): {json.dumps(payload, ensure_ascii=False, indent=2)[:2000]}")
        
        if trigger_id and SLACK_BOT_TOKEN:
            try:
                web_client = WebClient(token=SLACK_BOT_TOKEN)
                # channel과 message_ts를 모달에 전달하기 위해 private_metadata에 포함
                modal = create_resolve_modal(incident_id, incident_key, channel, message_ts)
                print(f"📝 모달 생성 완료: {json.dumps(modal, ensure_ascii=False)[:200]}...")
                
                result = web_client.views_open(
                    trigger_id=trigger_id,
                    view=modal
                )
                print(f"✅ Resolve 모달 열기 성공: incident_id={incident_id}")
                
                # 모달이 열렸으므로 응답만 보내고 종료
                response = SocketModeResponse(envelope_id=req.envelope_id)
                client.send_socket_mode_response(response)
                return
            except Exception as e:
                print(f"❌ 모달 열기 실패: {e}")
                import traceback
                traceback.print_exc()
                # 모달 열기 실패 시 기존 방식으로 처리 계속
        else:
            print(f"⚠️  모달 열기 조건 불만족: trigger_id={trigger_id}, SLACK_BOT_TOKEN={'있음' if SLACK_BOT_TOKEN else '없음'}")
    
    # 모달을 열지 않는 경우에만 응답 보내기
    response = SocketModeResponse(envelope_id=req.envelope_id)
    client.send_socket_mode_response(response)
    
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
            # 모달을 열 수 없는 경우 기존 방식으로 처리
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
        
        # Register handlers
        socket_client.socket_mode_request_listeners.append(handle_interactive_components)
        # reaction_added는 handle_interactive_components 내부에서 처리됨
        
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

