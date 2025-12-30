# Slack Socket Mode 아키텍처 및 동작 원리

## 핵심 답변

**Slack Socket Mode는 "내부에서 Slack으로 세션을 연결하는 구조"입니다.**

즉, 우리 애플리케이션이 Slack 서버에 **WebSocket 연결을 시작하고 유지**하며, Slack이 이벤트를 우리에게 전송하는 방식입니다.

---

## 1. 기본 구조

### 1.1 연결 방향

```
[우리 애플리케이션] ──WebSocket 연결 시작──> [Slack 서버]
         ↑                                        │
         │                                        │
         └──────────이벤트 수신───────────────┘
```

**중요**: 
- 우리가 Slack에 연결을 시작합니다 (Outbound Connection)
- Slack이 우리를 호출하는 것이 아닙니다
- 공개 URL (ngrok 등)이 필요 없습니다

### 1.2 연결 대상: Slack App 전체

**핵심 답변**: WebSocket은 **특정 채널이 아닌 Slack App 전체**와 연결됩니다.

```
[우리 애플리케이션]
    │
    │ WebSocket 연결
    │ (App-Level Token으로 인증)
    ↓
[Slack App 전체]
    │
    ├── 워크스페이스 A
    │   ├── 채널 #general
    │   ├── 채널 #incidents
    │   └── DM 채널들
    │
    └── 워크스페이스 B (멀티 워크스페이스인 경우)
        └── ...
```

**연결 범위**:
- **Slack App 전체**: 특정 채널이 아닌 App 레벨로 연결
- **워크스페이스 전체**: Bot이 접근 가능한 모든 채널의 이벤트 수신
- **모든 이벤트 타입**: 버튼 클릭, 리액션, 메시지 등

**채널 지정은 언제?**
- **이벤트 수신 시**: 이벤트 payload에 `channel` 정보가 포함됨
- **메시지 전송 시**: `channel` 파라미터로 특정 채널 지정

**예시**:
```python
# 이벤트 수신 (어떤 채널에서든 발생 가능)
payload = {
    "channel": {"id": "C0A4LAEF6P8"},  # 이벤트가 발생한 채널
    "actions": [...]
}

# 메시지 전송 (특정 채널 지정)
web_client.chat_postMessage(
    channel="C0A4LAEF6P8",  # 특정 채널로 전송
    text="Incident 발생"
)
```

### 1.2 전통적인 Webhook 방식과의 비교

#### Webhook 방식 (기존)
```
[Slack] ──HTTP POST──> [공개 URL (ngrok)] ──> [우리 서버]
```
- Slack이 우리를 호출
- 공개 URL 필요
- 방화벽/네트워크 설정 복잡

#### Socket Mode (현재)
```
[우리 서버] ──WebSocket 연결──> [Slack 서버]
         ↑                        │
         └────이벤트 수신─────────┘
```
- 우리가 Slack에 연결
- 공개 URL 불필요
- 방화벽/네트워크 설정 간단

---

## 2. 동작 원리

### 2.1 연결 시작

**코드 위치**: `slack_socket.py` - `start_socket_mode_client()`

```python
socket_client = SocketModeClient(
    app_token=app_token,  # App-Level Token (xapp-1-...)
    web_client=WebClient(token=bot_token) if bot_token else None
)

# 핸들러 등록
socket_client.socket_mode_request_listeners.append(handle_interactive_components)

# 연결 시작
socket_client.connect()
```

**동작 과정**:
1. `SocketModeClient` 인스턴스 생성
2. Slack 서버에 WebSocket 연결 시도
3. `app_token`으로 인증
4. 연결 성공 시 핸들러 등록
5. 연결 유지 (Keep-Alive)

**연결 대상**: `wss://wss-primary.slack.com/link` (Slack의 Socket Mode 엔드포인트)

---

### 2.2 연결 유지

**핵심**: WebSocket 연결이 **지속적으로 유지**됩니다

```
[애플리케이션 시작]
    ↓
[SocketModeClient.connect() 호출]
    ↓
[WebSocket 연결 수립]
    ↓
[연결 유지 (Keep-Alive)]
    ↓
[이벤트 대기...]
```

**Keep-Alive 메커니즘**:
- WebSocket 프레임을 주기적으로 교환하여 연결 유지
- 연결이 끊어지면 자동으로 재연결 시도

---

### 2.3 이벤트 수신

**Slack → 우리 애플리케이션**

Slack에서 이벤트가 발생하면 (예: 버튼 클릭, 이모티콘 리액션), Slack 서버가 WebSocket을 통해 우리에게 전송합니다.

**이벤트 타입**:
- `interactive`: 버튼 클릭, 모달 제출 등
- `events_api`: 이모티콘 리액션, 메시지 이벤트 등

**처리 흐름**:
```
[사용자가 버튼 클릭]
    ↓
[Slack 서버가 이벤트 생성]
    ↓
[WebSocket을 통해 우리에게 전송]
    ↓
[handle_interactive_components() 호출]
    ↓
[이벤트 처리 및 응답]
```

---

### 2.4 이벤트 처리 및 응답

**코드 위치**: `slack_socket.py` - `handle_interactive_components()`

```python
def handle_interactive_components(client: SocketModeClient, req: SocketModeRequest):
    # 1. Payload 파싱
    payload = req.payload
    action = payload.get("actions", [])[0]
    
    # 2. 이벤트 처리
    # ... (DB 작업, API 호출 등)
    
    # 3. 응답 전송
    response = SocketModeResponse(envelope_id=req.envelope_id)
    client.send_socket_mode_response(response)
```

**응답 구조**:
- `envelope_id`: Slack이 보낸 요청의 고유 ID
- 이 ID를 포함하여 응답하면 Slack이 요청을 받았다고 인식

**중요**: 
- 응답은 **동기적으로** 전송해야 합니다
- 응답이 없으면 Slack이 타임아웃 에러를 발생시킬 수 있습니다

---

## 3. 상세 동작 흐름

### 3.1 애플리케이션 시작 시

```
1. app.py 실행
   ↓
2. start_socket_mode_client() 호출
   ↓
3. SocketModeClient 생성
   ↓
4. WebSocket 연결 시작
   - URL: wss://wss-primary.slack.com/link
   - 인증: App-Level Token (xapp-1-...)
   ↓
5. 연결 성공
   ↓
6. 핸들러 등록
   - handle_interactive_components
   - handle_reaction_added
   - handle_view_submission
   ↓
7. 연결 유지 (백그라운드 스레드)
```

---

### 3.2 버튼 클릭 시

```
[사용자가 Slack에서 "👀 Ack" 버튼 클릭]
    ↓
[Slack 서버가 이벤트 생성]
    ↓
[WebSocket을 통해 우리 애플리케이션에 전송]
    {
        "type": "interactive",
        "envelope_id": "abc123",
        "payload": {
            "type": "block_actions",
            "actions": [{
                "action_id": "incident_ack",
                "value": "{\"incident_id\":\"INC-...\",\"action\":\"ack\"}"
            }]
        }
    }
    ↓
[handle_interactive_components() 호출]
    ↓
[Payload 파싱]
    - incident_id 추출
    - action_type 추출
    ↓
[DB 작업]
    - acknowledge_incident() 호출
    ↓
[Slack 스레드에 코멘트 전송]
    - WebClient.chat_postMessage() 사용
    ↓
[응답 전송]
    SocketModeResponse(envelope_id="abc123")
    ↓
[Slack이 응답 수신 확인]
```

---

### 3.3 이모티콘 리액션 시

```
[사용자가 메시지에 👀 이모티콘 추가]
    ↓
[Slack 서버가 reaction_added 이벤트 생성]
    ↓
[WebSocket을 통해 전송]
    {
        "type": "events_api",
        "envelope_id": "def456",
        "event": {
            "type": "reaction_added",
            "reaction": "eyes",
            "item": {"ts": "1767082368.206769"}
        }
    }
    ↓
[handle_reaction_added() 호출]
    ↓
[리액션 타입 확인]
    - "eyes" → "ack" 액션
    ↓
[메시지 조회하여 incident_id 추출]
    ↓
[DB 작업 및 응답]
```

---

## 4. 토큰 구조

### 4.1 App-Level Token (`SLACK_APP_TOKEN`)

**형식**: `xapp-1-...`

**용도**: Socket Mode 연결 인증

**권한**:
- `connections:write`: WebSocket 연결 생성

**설정 위치**: Slack App 설정 → "Socket Mode" → "Enable Socket Mode" → Token 생성

**중요**: 이 토큰만으로는 메시지 전송 불가

---

### 4.2 Bot User OAuth Token (`SLACK_BOT_TOKEN`)

**형식**: `xoxb-...`

**용도**: 
- 메시지 전송 (`chat_postMessage`)
- 모달 열기 (`views.open`)
- 메시지 조회 (`conversations_history`)

**권한** (OAuth Scopes):
- `chat:write`: 메시지 전송
- `channels:read`: 채널 정보 조회
- `users:read`: 사용자 정보 조회

**설정 위치**: Slack App 설정 → "OAuth & Permissions" → "Bot Token Scopes"

---

## 5. 네트워크 구조

### 5.1 연결 방향

```
[우리 서버 (Docker Container)]
    │
    │ Outbound Connection (우리가 시작)
    │
    ↓
[인터넷]
    │
    ↓
[Slack 서버 (wss://wss-primary.slack.com)]
```

**특징**:
- **Outbound 연결**: 우리가 Slack에 연결
- **방화벽**: Outbound 연결만 허용하면 됨
- **공개 IP 불필요**: 우리 서버가 공개 IP를 가질 필요 없음

---

### 5.2 WebSocket 프로토콜

**프로토콜**: WebSocket (WSS - WebSocket Secure)

**특징**:
- **양방향 통신**: 클라이언트와 서버 모두 메시지 전송 가능
- **지속 연결**: HTTP와 달리 연결이 유지됨
- **실시간**: 이벤트 발생 시 즉시 전송

**연결 유지**:
- Keep-Alive 메커니즘으로 연결 유지
- 연결 끊어지면 자동 재연결

---

## 6. 코드 분석

### 6.1 연결 시작 코드

```python
# slack_socket.py

def start_socket_mode_client(app_token: str, bot_token: str = None):
    # SocketModeClient 생성
    socket_client = SocketModeClient(
        app_token=app_token,  # App-Level Token
        web_client=WebClient(token=bot_token) if bot_token else None
    )
    
    # 핸들러 등록
    socket_client.socket_mode_request_listeners.append(handle_interactive_components)
    
    # 연결 시작 (여기서 WebSocket 연결 수립)
    socket_client.connect()
```

**핵심**: `socket_client.connect()` 호출 시 WebSocket 연결이 시작됩니다.

---

### 6.2 이벤트 수신 코드

```python
def handle_interactive_components(client: SocketModeClient, req: SocketModeRequest):
    # req는 Slack이 보낸 요청 객체
    payload = req.payload  # 이벤트 데이터
    
    # 이벤트 처리
    # ...
    
    # 응답 전송
    response = SocketModeResponse(envelope_id=req.envelope_id)
    client.send_socket_mode_response(response)
```

**핵심**: 
- `req`는 Slack이 WebSocket을 통해 전송한 요청
- `envelope_id`는 요청의 고유 ID
- 응답에 같은 `envelope_id`를 포함해야 함

---

## 7. 장점과 단점

### 7.1 장점

1. **공개 URL 불필요**
   - ngrok, 공개 IP 등 불필요
   - 내부 네트워크에서도 동작

2. **방화벽 설정 간단**
   - Outbound 연결만 허용하면 됨
   - Inbound 포트 오픈 불필요

3. **실시간 통신**
   - 이벤트 발생 시 즉시 수신
   - Webhook보다 빠름

4. **연결 안정성**
   - 자동 재연결 메커니즘
   - Keep-Alive로 연결 유지

---

### 7.2 단점

1. **연결 유지 필요**
   - 애플리케이션이 실행 중이어야 함
   - 연결이 끊어지면 이벤트 수신 불가

2. **리소스 사용**
   - WebSocket 연결 유지로 인한 메모리/네트워크 사용

3. **디버깅 복잡**
   - WebSocket 연결 상태 확인 필요
   - 로그 분석이 복잡할 수 있음

---

## 8. Webhook 방식과의 비교

### 8.1 Webhook 방식

**구조**:
```
[Slack] ──HTTP POST──> [공개 URL] ──> [우리 서버]
```

**특징**:
- Slack이 우리를 호출
- 공개 URL 필요 (ngrok 등)
- 방화벽에서 Inbound 포트 오픈 필요
- 이벤트 발생 시에만 연결 (Stateless)

**코드 예시**:
```python
@app.post("/webhook/slack")
async def slack_webhook(request: Request):
    # Slack이 우리를 호출
    payload = await request.json()
    # 처리...
```

---

### 8.2 Socket Mode 방식

**구조**:
```
[우리 서버] ──WebSocket──> [Slack 서버]
         ↑                    │
         └──이벤트 수신────────┘
```

**특징**:
- 우리가 Slack에 연결
- 공개 URL 불필요
- Outbound 연결만 필요
- 연결 유지 (Stateful)

**코드 예시**:
```python
socket_client = SocketModeClient(app_token=app_token)
socket_client.connect()  # 우리가 연결 시작

# 이벤트는 핸들러로 자동 수신
def handle_interactive_components(client, req):
    # Slack이 WebSocket을 통해 이벤트 전송
    pass
```

---

## 9. 실제 동작 확인

### 9.1 연결 상태 확인

**로그 확인**:
```bash
docker compose logs alert-receiver | grep "Socket Mode"
```

**예상 출력**:
```
✅ Slack Socket Mode 클라이언트 시작됨
```

---

### 9.2 이벤트 수신 확인

**로그 확인**:
```bash
docker compose logs alert-receiver | grep "Socket Mode 요청"
```

**예상 출력**:
```
📥 Socket Mode 요청 수신: type=interactive, envelope_id=abc123
```

---

## 10. WebSocket 연결 대상 상세

### 10.1 연결 대상: Slack App 전체

**Q: WebSocket은 특정 채널과 연결되는가?**
**A: 아닙니다. Slack App 전체와 연결됩니다.**

**구조**:
```
[우리 애플리케이션]
    │
    │ WebSocket 연결 (1개)
    │ App-Level Token (xapp-1-...)으로 인증
    ↓
[Slack App]
    │
    ├── 워크스페이스 전체
    │   ├── 모든 공개 채널
    │   ├── Bot이 초대된 비공개 채널
    │   ├── DM 채널
    │   └── 그룹 DM
    │
    └── 모든 이벤트 타입
        ├── interactive (버튼 클릭)
        ├── events_api (리액션, 메시지 등)
        └── view_submission (모달 제출)
```

### 10.2 채널별 필터링

**이벤트 수신 시**:
- WebSocket은 모든 채널의 이벤트를 수신
- 이벤트 payload에 `channel` 정보가 포함됨
- 핸들러에서 `channel`을 확인하여 필요한 이벤트만 처리

**코드 예시**:
```python
def handle_interactive_components(client, req):
    payload = req.payload
    channel = payload.get("channel", {}).get("id")  # 이벤트가 발생한 채널
    
    # 특정 채널만 처리하고 싶다면
    if channel != "C0A4LAEF6P8":
        return  # 다른 채널 이벤트는 무시
```

**메시지 전송 시**:
- `channel` 파라미터로 특정 채널 지정
- `SLACK_CHANNEL` 환경 변수로 기본 채널 설정 가능

**코드 예시**:
```python
# 특정 채널로 메시지 전송
web_client.chat_postMessage(
    channel="C0A4LAEF6P8",  # 특정 채널 지정
    text="Incident 발생"
)
```

### 10.3 실제 동작 예시

**시나리오 1: 여러 채널에 메시지 전송**
```
[알람 발생]
    ↓
[우리 애플리케이션이 메시지 생성]
    ↓
[특정 채널로 전송] (channel="C0A4LAEF6P8")
    ↓
[Slack App 전체 WebSocket으로 이벤트 수신 대기]
```

**시나리오 2: 어떤 채널에서든 버튼 클릭 가능**
```
[사용자가 채널 #general에서 버튼 클릭]
    ↓
[WebSocket으로 이벤트 수신]
    payload: {"channel": {"id": "C123456"}}
    ↓
[핸들러에서 처리]
    - channel 정보 확인
    - DB 작업 수행
    - 같은 채널에 응답 전송
```

**시나리오 3: 여러 채널에서 동시에 이벤트 발생**
```
[채널 #general에서 버튼 클릭]
    ↓
[WebSocket으로 이벤트 1 수신] → 처리
    ↓
[채널 #incidents에서 버튼 클릭]
    ↓
[WebSocket으로 이벤트 2 수신] → 처리
```

**중요**: 하나의 WebSocket 연결로 모든 채널의 이벤트를 처리합니다.

---

## 11. 요약

### 핵심 답변

**Q: Slack이 내부를 호출하는 구조인가요?**
**A: 아닙니다. 우리가 Slack에 연결하는 구조입니다.**

**Q: 내부에서 Slack으로 세션을 연결하는 구조인가요?**
**A: 맞습니다. 우리 애플리케이션이 Slack 서버에 WebSocket 연결을 시작하고 유지합니다.**

**Q: WebSocket은 특정 채널과 연결되는가?**
**A: 아닙니다. Slack App 전체와 연결되며, 워크스페이스 전체의 이벤트를 수신합니다. 특정 채널로 메시지를 보낼 때만 channel 파라미터를 지정합니다.**

### 동작 흐름

1. **애플리케이션 시작** → `socket_client.connect()` 호출
2. **WebSocket 연결 수립** → Slack 서버에 연결
3. **연결 유지** → Keep-Alive로 연결 유지
4. **이벤트 수신** → Slack이 WebSocket을 통해 이벤트 전송
5. **이벤트 처리** → 핸들러에서 처리
6. **응답 전송** → `SocketModeResponse`로 응답

### 네트워크 구조

```
[우리 서버] ──Outbound WebSocket──> [Slack 서버]
         ↑                              │
         └────────이벤트 수신────────────┘
```

**결론**: 우리가 Slack에 연결을 시작하고 유지하며, Slack이 이벤트를 우리에게 전송하는 구조입니다.

