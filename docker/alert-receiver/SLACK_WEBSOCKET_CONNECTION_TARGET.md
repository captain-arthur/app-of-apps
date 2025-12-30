# Slack Socket Mode WebSocket 연결 대상 상세 설명

## 핵심 답변

**WebSocket은 특정 채널이 아닌 Slack App 전체와 연결됩니다.**

---

## 1. 연결 구조

### 1.1 연결 대상

```
[우리 애플리케이션]
    │
    │ WebSocket 연결 (1개)
    │ App-Level Token (xapp-1-...)으로 인증
    ↓
[Slack App 전체]
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

**중요 포인트**:
- **1개의 WebSocket 연결**: 여러 채널을 위한 여러 연결이 아닙니다
- **App 레벨 연결**: 특정 채널이 아닌 App 전체와 연결
- **모든 채널 이벤트 수신**: Bot이 접근 가능한 모든 채널의 이벤트를 수신

---

## 2. 채널과의 관계

### 2.1 WebSocket 연결 ≠ 채널 연결

**오해**: "WebSocket이 특정 채널과 연결된다"
**실제**: "WebSocket이 App 전체와 연결되고, 이벤트에 채널 정보가 포함됨"

**비유**:
- WebSocket = 전화선 (1개)
- 채널 = 전화를 받을 수 있는 모든 곳
- 이벤트 = 전화가 오는 곳의 주소 정보 포함

### 2.2 채널 정보는 이벤트에 포함

**이벤트 수신 시**:
```json
{
    "type": "interactive",
    "payload": {
        "channel": {
            "id": "C0A4LAEF6P8"  // 이벤트가 발생한 채널
        },
        "actions": [...]
    }
}
```

**코드에서 확인**:
```python
def handle_interactive_components(client, req):
    payload = req.payload
    channel = payload.get("channel", {}).get("id")  # 이벤트가 발생한 채널
    
    print(f"이벤트 발생 채널: {channel}")
    # 출력: "이벤트 발생 채널: C0A4LAEF6P8"
```

---

## 3. 실제 동작 예시

### 3.1 시나리오: 여러 채널에서 버튼 클릭

**상황**:
- 채널 #general에 Incident 메시지 전송
- 채널 #incidents에도 Incident 메시지 전송
- 두 채널 모두에서 버튼 클릭 가능

**동작**:
```
[WebSocket 연결] (1개)
    │
    ├── 채널 #general에서 버튼 클릭
    │   └── 이벤트 수신: {"channel": {"id": "C123456"}}
    │
    └── 채널 #incidents에서 버튼 클릭
        └── 이벤트 수신: {"channel": {"id": "C789012"}}
```

**코드 처리**:
```python
def handle_interactive_components(client, req):
    payload = req.payload
    channel = payload.get("channel", {}).get("id")
    
    # 어떤 채널에서든 처리 가능
    if channel == "C123456":  # #general
        print("채널 #general에서 버튼 클릭")
    elif channel == "C789012":  # #incidents
        print("채널 #incidents에서 버튼 클릭")
    
    # 같은 채널에 응답 전송
    web_client.chat_postMessage(
        channel=channel,  # 이벤트가 발생한 채널
        thread_ts=message_ts,
        text="처리 완료"
    )
```

---

### 3.2 시나리오: 특정 채널만 처리

**상황**: 특정 채널(#incidents)의 이벤트만 처리하고 싶음

**코드**:
```python
def handle_interactive_components(client, req):
    payload = req.payload
    channel = payload.get("channel", {}).get("id")
    
    # 특정 채널만 처리
    if channel != "C0A4LAEF6P8":  # #incidents 채널 ID
        print(f"다른 채널 이벤트 무시: {channel}")
        return  # 처리하지 않음
    
    # #incidents 채널 이벤트만 처리
    # ...
```

**결과**:
- WebSocket은 모든 채널의 이벤트를 수신
- 핸들러에서 특정 채널만 필터링하여 처리

---

## 4. 메시지 전송 시 채널 지정

### 4.1 메시지 전송은 채널 지정 필요

**WebSocket 연결**: App 전체 (채널 지정 불필요)
**메시지 전송**: 특정 채널 지정 필요

**코드 예시**:
```python
# 메시지 전송 시 채널 지정
web_client.chat_postMessage(
    channel="C0A4LAEF6P8",  # 특정 채널 지정
    text="Incident 발생"
)

# 또는 환경 변수 사용
SLACK_CHANNEL = "C0A4LAEF6P8"
web_client.chat_postMessage(
    channel=SLACK_CHANNEL,
    text="Incident 발생"
)
```

---

## 5. App-Level Token의 역할

### 5.1 App-Level Token (xapp-1-...)

**용도**: WebSocket 연결 인증

**권한**:
- `connections:write`: WebSocket 연결 생성
- App 전체 레벨 권한 (채널별 권한 아님)

**특징**:
- App 전체와 연결
- 모든 채널의 이벤트 수신 가능
- 메시지 전송 권한 없음 (Bot Token 필요)

---

### 5.2 Bot Token (xoxb-...)과의 차이

**App-Level Token**:
- WebSocket 연결용
- 이벤트 수신용
- 메시지 전송 불가

**Bot Token**:
- 메시지 전송용 (`chat_postMessage`)
- 채널 정보 조회용 (`conversations_history`)
- 사용자 정보 조회용 (`users.info`)

**사용 예시**:
```python
# App-Level Token: WebSocket 연결
socket_client = SocketModeClient(
    app_token="xapp-1-..."  # 연결용
)

# Bot Token: 메시지 전송
web_client = WebClient(token="xoxb-...")  # 메시지 전송용
web_client.chat_postMessage(
    channel="C0A4LAEF6P8",
    text="메시지"
)
```

---

## 6. 실제 코드 분석

### 6.1 연결 시작 코드

```python
# slack_socket.py

def start_socket_mode_client(app_token: str, bot_token: str = None):
    socket_client = SocketModeClient(
        app_token=app_token,  # App-Level Token (App 전체 연결)
        web_client=WebClient(token=bot_token) if bot_token else None
    )
    
    socket_client.connect()  # App 전체와 연결
```

**분석**:
- `app_token`으로 App 전체와 연결
- 채널 지정 없음
- 모든 채널의 이벤트 수신 가능

---

### 6.2 이벤트 수신 코드

```python
def handle_interactive_components(client, req):
    payload = req.payload
    
    # 이벤트가 발생한 채널 정보 추출
    channel = payload.get("channel", {}).get("id")
    
    # 이벤트 처리
    # ...
    
    # 같은 채널에 응답 전송
    web_client.chat_postMessage(
        channel=channel,  # 이벤트가 발생한 채널
        thread_ts=message_ts,
        text="처리 완료"
    )
```

**분석**:
- 이벤트 payload에서 채널 정보 추출
- 이벤트가 발생한 채널에 응답 전송

---

## 7. 요약

### 핵심 개념

1. **WebSocket 연결**: App 전체와 연결 (채널별 연결 아님)
2. **이벤트 수신**: 모든 채널의 이벤트를 수신 (이벤트에 채널 정보 포함)
3. **메시지 전송**: 특정 채널 지정 필요

### 비유

**WebSocket = 전화선 (1개)**
- 하나의 전화선으로 모든 곳과 통신

**채널 = 전화를 받을 수 있는 곳들**
- 여러 곳에서 전화가 올 수 있음
- 전화가 올 때 어디서 왔는지 알 수 있음

**이벤트 = 전화**
- 전화가 올 때 발신지 정보 포함
- 발신지에 따라 다르게 처리 가능

### 실제 동작

```
[WebSocket 연결] (1개, App 전체)
    │
    ├── 채널 A 이벤트 수신 → 처리
    ├── 채널 B 이벤트 수신 → 처리
    └── 채널 C 이벤트 수신 → 처리
```

**결론**: WebSocket은 특정 채널이 아닌 Slack App 전체와 연결되며, 모든 채널의 이벤트를 수신할 수 있습니다.

