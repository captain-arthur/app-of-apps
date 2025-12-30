# Incident Management System - 핵심 가이드

## 목차

1. [시스템 개요](#시스템-개요)
2. [Grafana 모듈](#1-grafana-모듈)
3. [Database 모듈](#2-database-모듈)
4. [Slack 모듈](#3-slack-모듈)
5. [AI 모듈](#4-ai-모듈)
6. [전체 워크플로우](#전체-워크플로우)
7. [환경 변수 설정](#환경-변수-설정)

---

## 시스템 개요

### 목적
Grafana에서 발생한 알람을 수신하여, 데이터베이스에 저장하고 Slack으로 전송하며, AI 분석을 통해 조치 제안을 제공하는 통합 Incident 관리 시스템입니다.

### 아키텍처
```
Grafana Alert → Webhook → FastAPI → MySQL → Slack → AI Analysis
```

### 핵심 개념

**Incident Key (사건 유형 키)**
- 같은 유형의 알람을 그룹화하는 키
- `rule_uid|cluster|namespace|phase` → SHA256 → 16자리 해시
- **왜 필요한가?**: 알람 폭발 방지, 같은 문제의 반복 알람을 하나의 Incident로 관리

**Incident ID (에피소드 ID)**
- 각 Incident 발생 시마다 새로 생성되는 고유 ID
- 형식: `INC-YYYYMMDDHHMMSS-{random_hex}`
- **왜 필요한가?**: 같은 유형의 알람이라도 시간이 지나 다시 발생하면 새로운 Incident로 관리

**Status (상태)**
- `active`: 활성 상태 (처리 중)
- `acknowledged`: 인지됨 (담당자가 확인)
- `resolved`: 해결됨

---

## 1. Grafana 모듈

### 1.1 개념과 목적

**목적**: Grafana Alerting 시스템과의 통합
- Grafana에서 발생한 알람을 Webhook으로 수신
- Grafana Silence API를 통해 알람 음소거 기능 제공

**파일**: `app.py`, `grafana_silence.py`

### 1.2 주요 함수

#### `extract_alert_info(alert: Dict[str, Any]) -> Dict[str, Any]`
**목적**: Grafana webhook payload에서 알람 정보 추출

**입력**:
```python
{
    "labels": {
        "alertname": "HighCPU",
        "cluster": "prod",
        "namespace": "default",
        "severity": "critical"
    },
    "annotations": {
        "description": "CPU usage is high"
    }
}
```

**출력**:
```python
{
    "rule_uid": "abc123",
    "alertname": "HighCPU",
    "state": "firing",
    "severity": "critical",
    "cluster": "prod",
    "namespace": "default",
    "phase": "production",
    "service": "api-server",
    "message": "CPU usage is high"
}
```

**사용 예시**:
```python
alert_info = extract_alert_info(alert_payload)
```

**왜 필요한가?**: Grafana의 복잡한 payload 구조를 단순화하여 시스템 내부에서 일관되게 사용

---

#### `calculate_incident_key(labels: Dict[str, Any]) -> str`
**목적**: 같은 유형의 알람을 그룹화하는 키 생성

**알고리즘**:
1. `rule_uid` (없으면 `alertname`) 추출
2. `cluster`, `namespace`, `phase` 추출
3. `|`로 연결: `rule_uid|cluster|namespace|phase`
4. SHA256 해시 생성
5. 앞 16자리 반환

**예시**:
```python
labels = {
    "rule_uid": "cpu-high",
    "cluster": "prod",
    "namespace": "default",
    "phase": "production"
}
# → "cpu-high|prod|default|production" → SHA256 → "a7f3e4670f9d5f66"
```

**주의사항**:
- `service`, `pod`, `node`, `instance`는 포함하지 않음
- **이유**: 알람 폭발 방지 (같은 namespace의 같은 알람은 하나로 그룹화)

**사용 예시**:
```python
incident_key = calculate_incident_key(alert_labels)
```

---

#### `create_grafana_silence(...) -> Optional[str]`
**목적**: Grafana Alertmanager에 Silence 생성 (알람 음소거)

**파일**: `grafana_silence.py`

**매개변수**:
- `alertname`: 알람 이름 (필수)
- `cluster`, `namespace`, `phase`, `service`: 선택적 필터
- `duration_minutes`: 음소거 시간 (기본: 30분)
- `comment`: 주석

**동작 방식**:
1. Matchers 생성 (labels 기반 필터)
2. 시작/종료 시간 계산
3. Grafana API 호출: `POST /api/alertmanager/grafana/api/v2/silences`

**API 엔드포인트**:
```
POST {GRAFANA_URL}/api/alertmanager/grafana/api/v2/silences
```

**요청 예시**:
```json
{
    "matchers": [
        {"name": "alertname", "value": "HighCPU", "isRegex": false},
        {"name": "cluster", "value": "prod", "isRegex": false}
    ],
    "startsAt": "2025-12-30T17:00:00.000Z",
    "endsAt": "2025-12-30T17:30:00.000Z",
    "comment": "Muted from Slack by user123 for 30 minutes",
    "createdBy": "Slack Bot"
}
```

**환경 변수**:
- `GRAFANA_URL`: Grafana 서버 URL (기본: `http://host.docker.internal:32570`)
- `GRAFANA_USER`: Grafana 사용자명 (기본: `admin`)
- `GRAFANA_PASSWORD`: Grafana 비밀번호 (기본: `admin`)

**사용 예시**:
```python
silence_id = create_grafana_silence(
    alertname="HighCPU",
    cluster="prod",
    namespace="default",
    duration_minutes=30,
    comment="Muted from Slack"
)
```

**왜 필요한가?**: Slack에서 직접 알람을 음소거하여 일시적으로 알람 노이즈를 줄임

---

#### `mute_incident_via_grafana(...) -> bool`
**목적**: Incident를 Grafana Silence로 음소거하는 래퍼 함수

**매개변수**:
- `alertname`, `cluster`, `namespace`, `phase`, `service`: 알람 필터
- `duration_minutes`: 음소거 시간
- `user`: 사용자명 (주석에 포함)

**사용 예시**:
```python
success = mute_incident_via_grafana(
    alertname="HighCPU",
    cluster="prod",
    namespace="default",
    duration_minutes=30,
    user="john.doe"
)
```

---

### 1.3 Webhook 엔드포인트

#### `POST /webhook/grafana`
**목적**: Grafana에서 알람을 수신하는 엔드포인트

**요청 형식**: Grafana Alerting Webhook JSON

**처리 흐름**:
1. Webhook payload 수신
2. 각 알람에 대해:
   - `extract_alert_info()`: 알람 정보 추출
   - `calculate_incident_key()`: Incident Key 계산
   - `find_or_create_incident()`: Incident 찾기 또는 생성
   - `save_alert_to_db()`: 알람 DB 저장
   - `send_to_slack()`: Slack 전송

**응답 형식**:
```json
{
    "status": "success",
    "results": [
        {
            "alert_id": 123,
            "incident_id": "INC-20251230170000-abc123",
            "incident_key": "a7f3e4670f9d5f66",
            "is_new_incident": true,
            "alert_count": 1
        }
    ]
}
```

---

## 2. Database 모듈

### 2.1 개념과 목적

**목적**: Incident와 알람 데이터의 영구 저장 및 관리

**데이터베이스**: MySQL (InnoDB 엔진)

**파일**: `app.py`, `incident_service.py`, `mysql/init/01-init-database.sql`

### 2.2 데이터베이스 스키마

#### `incidents` 테이블
**목적**: Incident (사건) 관리

**핵심 컬럼**:
- `incident_id` (PK): 에피소드 ID (예: `INC-20251230170000-abc123`)
- `incident_key`: 사건 유형 키 (16자리 해시)
- `status`: 상태 (`active`, `acknowledged`, `resolved`)
- `severity`: 심각도 (`critical`, `warning`, `info`)
- `alert_count`: 연결된 알람 개수 (트리거로 자동 업데이트)
- `slack_message_ts`: Slack 메시지 timestamp (스레드 루트)
- `action_taken`: 조치 내용 (Resolve 모달에서 입력)
- `root_cause`: 근본 원인 (Resolve 모달에서 입력)

**인덱스**:
- `idx_incident_key`: Incident Key 조회
- `idx_incident_key_status_last_seen`: 복합 인덱스 (같은 유형의 open incident 조회 최적화)

**트리거**:
- `trg_update_alert_count_on_insert`: 알람 추가 시 `alert_count` 자동 업데이트
- `trg_update_alert_count_on_delete`: 알람 삭제 시 `alert_count` 자동 업데이트
- `trg_prevent_duplicate_open_incident`: 같은 `incident_key`에 여러 open incident 방지

---

#### `grafana_alerts` 테이블
**목적**: 원본 알람 데이터 저장 (모든 알람을 무조건 저장)

**핵심 컬럼**:
- `alert_id` (PK): 자동 증가 ID
- `incident_id` (FK): 연결된 Incident ID
- `incident_key`: 사건 유형 키 (조회 편의용)
- `received_at`: 수신 시각
- `state`: 알람 상태 (`firing`, `resolved`)
- `alertname`: 알람 이름
- `labels`: 알람 라벨 (JSON)
- `annotations`: 알람 어노테이션 (JSON)
- `raw_payload`: 원본 Grafana payload 전체 (JSON)

**인덱스**:
- `idx_incident_id`: Incident별 알람 조회
- `idx_incident_key_received_at`: Incident Key와 수신 시각 복합 인덱스

**외래 키**:
- `incident_id` → `incidents.incident_id` (ON DELETE RESTRICT)

---

### 2.3 주요 함수

#### `get_db_connection() -> pymysql.Connection`
**목적**: MySQL 데이터베이스 연결 생성

**환경 변수**:
- `DB_HOST`: 호스트 (기본: `mysql`)
- `DB_PORT`: 포트 (기본: `3306`)
- `DB_USER`: 사용자명 (기본: `observer`)
- `DB_PASSWORD`: 비밀번호 (기본: `observer123`)
- `DB_NAME`: 데이터베이스명 (기본: `observer`)

**설정**:
- `charset='utf8mb4'`: UTF-8 완전 지원
- `cursorclass=pymysql.cursors.DictCursor`: 결과를 딕셔너리로 반환

**사용 예시**:
```python
conn = get_db_connection()
try:
    # DB 작업
    pass
finally:
    conn.close()
```

---

#### `find_or_create_incident(conn, incident_key: str, alert_info: Dict) -> tuple[str, bool]`
**목적**: Open Incident 찾기 또는 새로 생성

**파일**: `app.py`

**알고리즘**:
1. 같은 `incident_key`의 open incident 조회 (`SELECT FOR UPDATE`)
2. 있으면: 기존 Incident 사용, `last_seen_at` 업데이트 → `(incident_id, False)`
3. 없으면: 새 Incident 생성 → `(incident_id, True)`

**동시성 처리**:
- `SELECT FOR UPDATE`: Row Lock으로 동시성 문제 해결
- 같은 `incident_key`로 동시 요청 시 하나만 처리

**트랜잭션**:
- `commit`은 호출자에서 처리 (트랜잭션 범위 확대)

**사용 예시**:
```python
incident_id, is_new = find_or_create_incident(conn, incident_key, alert_info)
```

**왜 필요한가?**: 같은 유형의 알람이 반복 발생해도 하나의 Incident로 관리

---

#### `save_alert_to_db(conn, alert_info, raw_payload, incident_id, incident_key) -> int`
**목적**: 알람을 `grafana_alerts` 테이블에 저장

**파일**: `app.py`

**저장 데이터**:
- `incident_id`, `incident_key`: Incident 연결
- `received_at`: 수신 시각
- `state`: 알람 상태
- `alertname`, `message`: 알람 정보
- `labels`, `annotations`: JSON 형식으로 저장
- `raw_payload`: 원본 payload 전체 저장

**트랜잭션**:
- `commit`은 호출자에서 처리

**반환값**: `alert_id` (자동 증가 ID)

**사용 예시**:
```python
alert_id = save_alert_to_db(conn, alert_info, raw_payload, incident_id, incident_key)
```

**왜 필요한가?**: 모든 알람을 영구 저장하여 추후 분석 및 감사 가능

---

#### `acknowledge_incident(conn, incident_id: str, user: str) -> bool`
**목적**: Incident를 Acknowledged 상태로 변경

**파일**: `incident_service.py`

**업데이트 내용**:
- `status = 'acknowledged'`
- `acknowledged_time = NOW()`
- `acknowledged_by = user`
- `updated_at = NOW()`

**트랜잭션**:
- `commit`은 호출자에서 처리

**사용 예시**:
```python
success = acknowledge_incident(conn, incident_id, "john.doe")
```

**왜 필요한가?**: 담당자가 Incident를 확인했음을 표시

---

#### `resolve_incident(conn, incident_id: str, user: str) -> bool`
**목적**: Incident를 Resolved 상태로 변경

**파일**: `incident_service.py`

**업데이트 내용**:
- `status = 'resolved'`
- `resolved_time = NOW()`
- `resolved_by = user`
- `updated_at = NOW()`

**주의**: `action_taken`과 `root_cause`는 별도로 업데이트 (Resolve 모달에서)

**트랜잭션**:
- `commit`은 호출자에서 처리

**사용 예시**:
```python
success = resolve_incident(conn, incident_id, "john.doe")
```

**왜 필요한가?**: Incident 해결 완료 표시

---

#### `get_incident_info(conn, incident_id: str) -> Optional[Dict]`
**목적**: Incident 정보 조회

**파일**: `incident_service.py`

**조회 컬럼**:
- `incident_id`, `incident_key`, `status`, `severity`
- `cluster`, `namespace`, `phase`, `service`
- `alert_count`, `start_time`, `first_seen_at`

**사용 예시**:
```python
incident_info = get_incident_info(conn, incident_id)
if incident_info:
    print(f"Status: {incident_info['status']}")
```

---

### 2.4 트리거 (Trigger)

#### `trg_update_alert_count_on_insert`
**목적**: 알람 추가 시 `incidents.alert_count` 자동 업데이트

**동작**: `grafana_alerts`에 INSERT 시 → 해당 `incident_id`의 알람 개수 재계산

**왜 필요한가?**: 애플리케이션 레벨에서 수동 계산 불필요, 데이터 일관성 보장

---

#### `trg_prevent_duplicate_open_incident`
**목적**: 같은 `incident_key`에 여러 open incident 방지

**동작**: `incidents`에 INSERT 전 체크 → 이미 open incident가 있으면 에러 발생

**왜 필요한가?**: 데이터 무결성 보장, 같은 유형의 알람이 하나의 Incident로 관리되도록 보장

---

## 3. Slack 모듈

### 3.1 개념과 목적

**목적**: Slack을 통한 Incident 알림 및 상호작용

**주요 기능**:
- Incident 메시지 전송 (Block Kit)
- 버튼 클릭 처리 (Ack, Resolve, AI 분석, Mute)
- 이모티콘 리액션 처리
- 모달 창 (Resolve 시 조치 내용 입력)
- 스레드 코멘트 (AI 분석 결과 등)

**파일**: 
- `slack_sender.py`: 메시지 전송
- `slack_socket.py`: Socket Mode 클라이언트 (버튼/리액션 처리)
- `slack_interactions.py`: Webhook 기반 인터랙션 (사용 안 함)

---

### 3.2 Slack Block Kit

**개념**: Slack의 리치 메시지 UI 프레임워크

**주요 블록 타입**:
- `header`: 제목
- `section`: 텍스트/필드 표시
- `context`: 보조 정보
- `divider`: 구분선
- `actions`: 버튼 그룹

---

### 3.3 주요 함수

#### `create_incident_card(...) -> Dict[str, Any]`
**목적**: Incident Block Kit 카드 생성

**파일**: `slack_sender.py`

**매개변수**:
- `incident_id`, `incident_key`: Incident 식별자
- `status`, `severity`: 상태 및 심각도
- `cluster`, `namespace`, `phase`, `service`: 환경 정보
- `alert_count`: 알람 개수
- `start_time`: 발생 시각
- `is_new_incident`: 신규 여부

**생성되는 블록**:
1. **Header**: `🚨 Incident 발생`
2. **Section 1**: Incident ID, Status, Severity, Alerts
3. **Section 2**: Cluster, Namespace, Phase, Service
4. **Context**: 발생 시각, Signature
5. **Divider**
6. **Actions**: 버튼들
   - `👀 Ack` (primary)
   - `✅ Resolve` (danger)
   - `🤖 AI 분석`
   - `🔕 Mute 30m`
   - `🔕 Mute 2h`
   - `🔕 Mute 24h`

**버튼 Value 구조**:
```json
{
    "incident_id": "INC-20251230170000-abc123",
    "incident_key": "a7f3e4670f9d5f66",
    "action": "ack"  // 또는 "resolve", "ai_analysis", "mute_30m" 등
}
```

**사용 예시**:
```python
blocks = create_incident_card(
    incident_id="INC-20251230170000-abc123",
    incident_key="a7f3e4670f9d5f66",
    status="active",
    severity="critical",
    cluster="prod",
    namespace="default",
    phase="production",
    service="api-server",
    alert_count=5,
    start_time=datetime.now(),
    is_new_incident=True
)
```

---

#### `send_incident_card(blocks: Dict, channel: str = None) -> Optional[str]`
**목적**: Slack에 Incident 카드 전송

**파일**: `slack_sender.py`

**전송 방식**:
1. **Webhook 방식** (우선):
   - `SLACK_WEBHOOK_URL`이 있으면 사용
   - 단순하고 빠름
   - 단점: `ts` (timestamp) 반환 안 됨

2. **WebClient 방식** (대체):
   - `SLACK_BOT_TOKEN` 사용
   - `chat_postMessage` API 호출
   - 장점: `ts` 반환 가능 (스레드 코멘트에 필요)

**환경 변수**:
- `SLACK_WEBHOOK_URL`: Incoming Webhook URL
- `SLACK_BOT_TOKEN`: Bot User OAuth Token (`xoxb-...`)
- `SLACK_CHANNEL`: 기본 채널 ID (기본: `C0A4LAEF6P8`)

**반환값**: `ts` (메시지 timestamp) 또는 `None`

**사용 예시**:
```python
ts = send_incident_card(blocks)
if ts:
    print(f"메시지 전송 성공: {ts}")
```

**왜 필요한가?**: Incident 정보를 Slack에 표시하여 팀에게 알림

---

#### `send_thread_reply(thread_ts: str, text: str, channel: str = None) -> bool`
**목적**: Slack 스레드에 코멘트 추가

**파일**: `slack_sender.py`

**매개변수**:
- `thread_ts`: 스레드 루트 메시지의 timestamp
- `text`: 코멘트 텍스트
- `channel`: 채널 ID

**전송 방식**:
1. Webhook 방식 (우선)
2. WebClient 방식 (대체)

**사용 예시**:
```python
send_thread_reply(
    thread_ts="1767082368.206769",
    text="🤖 AI 분석 결과\n\n조치 제안: ...",
    channel="C0A4LAEF6P8"
)
```

**왜 필요한가?**: AI 분석 결과나 사용자 액션 결과를 스레드에 추가

---

### 3.4 Slack Socket Mode

**개념**: Slack의 실시간 통신 방식
- WebSocket 기반
- 공개 URL (ngrok) 불필요
- 버튼 클릭, 이모티콘 리액션 실시간 처리

**환경 변수**:
- `SLACK_APP_TOKEN`: App-Level Token (`xapp-...`)
- `SLACK_BOT_TOKEN`: Bot User OAuth Token (`xoxb-...`)

---

#### `start_socket_mode_client(app_token: str, bot_token: str = None)`
**목적**: Slack Socket Mode 클라이언트 시작

**파일**: `slack_socket.py`

**등록되는 핸들러**:
- `handle_interactive_components`: 버튼 클릭 처리
- `handle_reaction_added`: 이모티콘 리액션 처리
- `handle_view_submission`: 모달 제출 처리

**사용 예시**:
```python
start_socket_mode_client(
    app_token="xapp-1-...",
    bot_token="xoxb-..."
)
```

**왜 필요한가?**: 버튼 클릭과 리액션을 실시간으로 처리

---

#### `handle_interactive_components(client, req)`
**목적**: 버튼 클릭 처리

**파일**: `slack_socket.py`

**처리 액션**:
- `ack`: Incident ACK
- `resolve`: Resolve 모달 열기 또는 직접 Resolve
- `ai_analysis`: AI 분석 실행
- `mute_30m`, `mute_2h`, `mute_24h`: Grafana Silence 생성

**처리 흐름**:
1. Payload 파싱 (`incident_id`, `action_type` 추출)
2. `resolve` 액션: 모달 열기 (우선)
3. DB 연결 및 트랜잭션 시작
4. 액션별 처리:
   - `ack`: `acknowledge_incident()` 호출
   - `resolve`: `resolve_incident()` 호출
   - `ai_analysis`: 백그라운드 스레드에서 AI 분석
   - `mute_*`: `mute_incident_via_grafana()` 호출
5. Slack 스레드에 결과 코멘트 전송

**사용 예시**: 자동 호출 (Socket Mode)

---

#### `handle_reaction_added(client, req)`
**목적**: 이모티콘 리액션 처리

**파일**: `slack_socket.py`

**리액션 매핑**:
- `eyes` (👀) → `ack`
- `white_check_mark` (✅) → `resolve`
- `no_bell` (🔕) → `mute_30m`

**처리 흐름**:
1. 리액션 타입 확인
2. 메시지 조회하여 `incident_id` 추출
3. `process_incident_action()` 호출

**사용 예시**: 자동 호출 (Socket Mode)

---

#### `create_resolve_modal(incident_id, incident_key, channel, message_ts) -> dict`
**목적**: Resolve 모달 생성

**파일**: `slack_socket.py`

**모달 구성**:
- Incident ID, Signature 표시
- `action_taken`: 조치 내용 입력 (multiline, optional)
- `root_cause`: 근본 원인 입력 (multiline, optional)

**사용 예시**: `handle_interactive_components`에서 자동 호출

---

#### `handle_view_submission(client, req)`
**목적**: 모달 제출 처리

**파일**: `slack_socket.py`

**처리 내용**:
1. `action_taken`, `root_cause` 추출
2. `incidents` 테이블 업데이트
3. `resolve_incident()` 호출
4. Slack 스레드에 결과 코멘트 전송

**사용 예시**: 자동 호출 (Socket Mode)

---

### 3.5 메시지 전송 전략

**신규 Incident**:
- 새 메시지 전송
- `ts` 저장 (`slack_message_ts`)

**기존 Incident**:
- 새 메시지 전송 안 함
- 기존 메시지의 `ts` 사용
- AI 코멘트는 같은 스레드에 추가

**왜 이렇게 하나?**: 같은 Incident의 모든 정보가 하나의 스레드에 모이도록 함

---

## 4. AI 모듈

### 4.1 개념과 목적

**목적**: AI를 활용한 Incident 분석 및 조치 제안

**기술 스택**:
- **LangChain**: LLM 프레임워크
- **Ollama**: 로컬 LLM 실행 환경
- **Mistral**: LLM 모델 (현재 설정)

**파일**: `incident_ai.py`

---

### 4.2 주요 함수

#### `get_ai_llm() -> Optional[Ollama]`
**목적**: Ollama LLM 인스턴스 생성

**환경 변수**:
- `OLLAMA_BASE_URL`: Ollama 서버 URL (기본: `http://localhost:11434`)
- `OLLAMA_MODEL`: 모델명 (기본: `mistral`)

**설정**:
- `temperature=0.7`: 일관성과 창의성의 조화

**사용 예시**:
```python
llm = get_ai_llm()
if llm:
    # LLM 사용 가능
    pass
```

---

#### `analyze_incident(incident_info: Dict, alerts: list) -> Dict[str, str]`
**목적**: Incident를 AI로 분석하여 조치 제안 및 근본 원인 분석

**매개변수**:
- `incident_info`: Incident 정보 (ID, severity, cluster 등)
- `alerts`: 관련 알람 리스트 (최대 10개)

**반환값**:
```python
{
    "action_taken_suggestion": "조치 제안 내용 (한글)",
    "root_cause_analysis": "근본 원인 분석 (한글)",
    "similar_incidents": "유사 사건 패턴 (한글, 없으면 '없음')"
}
```

**처리 흐름**:
1. 알람 정보 요약 (최대 5개, 메시지 200자 제한)
2. Incident 정보 포맷팅
3. LangChain PromptTemplate 생성
4. LLMChain 실행
5. JSON 파싱 (마크다운 코드 블록 제거)
6. 결과 반환

**프롬프트 원리**:
- **역할 기반**: "Google SRE 원칙을 따르는 DevOps 엔지니어"
- **Few-Shot Learning**: JSON 형식 예시 제공
- **제약 조건**: 한글 작성 필수, 구체성 요구

**사용 예시**:
```python
analysis = analyze_incident(incident_info, alerts)
if analysis.get("action_taken_suggestion"):
    print(analysis["action_taken_suggestion"])
```

**왜 필요한가?**: 빠른 조치 제안 및 근본 원인 파악 지원

---

#### `get_incident_analysis_for_modal(incident_id: str, conn) -> Dict[str, str]`
**목적**: Resolve 모달을 위한 AI 분석 결과 반환

**반환값**:
```python
{
    "action_taken_suggestion": "조치 제안",
    "root_cause_analysis": "근본 원인 분석"
}
```

**사용 예시**: Resolve 모달에 AI 제안을 미리 채우는 용도 (현재 미사용)

---

### 4.3 AI 분석 실행 시점

**버튼 클릭 시**:
- 사용자가 "🤖 AI 분석" 버튼 클릭
- 백그라운드 스레드에서 실행
- 완료 후 스레드에 코멘트 추가

**자동 실행**: 없음 (버튼 클릭 시에만 실행)

---

### 4.4 프롬프트 구조

**입력 데이터**:
- `incident_context`: Incident 정보 (ID, severity, cluster 등)
- `alert_summary`: 관련 알람 요약 (JSON)

**출력 형식**: JSON
```json
{
    "action_taken_suggestion": "한글로 작성된 구체적인 조치 제안 (2-4줄, 우선순위 포함)",
    "root_cause_analysis": "한글로 작성된 근본 원인 분석 (2-4줄)",
    "similar_incidents": "한글로 작성된 유사 사건 패턴 설명 (없으면 '없음')"
}
```

**지침**:
1. Google SRE의 "Blameless Postmortem" 원칙 준수
2. 모든 응답은 한글로 작성
3. 조치 제안은 구체적이고 실행 가능해야 함
4. 근본 원인 분석은 종합적으로 고려

**자세한 내용**: `AI_PROMPT_ARCHITECTURE.md` 참조

---

## 전체 워크플로우

### 1. 알람 수신 및 처리

```
Grafana Alert 발생
    ↓
POST /webhook/grafana
    ↓
extract_alert_info() → 알람 정보 추출
    ↓
calculate_incident_key() → Incident Key 계산
    ↓
find_or_create_incident() → Incident 찾기/생성
    ↓
save_alert_to_db() → 알람 DB 저장
    ↓
send_to_slack() → Slack 전송
```

### 2. 버튼 클릭 처리

```
사용자가 버튼 클릭 (예: "👀 Ack")
    ↓
Slack Socket Mode → handle_interactive_components()
    ↓
액션 타입 확인 (ack/resolve/ai_analysis/mute)
    ↓
DB 연결 및 트랜잭션 시작
    ↓
액션별 처리:
  - ack → acknowledge_incident()
  - resolve → create_resolve_modal() 또는 resolve_incident()
  - ai_analysis → 백그라운드 스레드에서 analyze_incident()
  - mute → mute_incident_via_grafana()
    ↓
Slack 스레드에 결과 코멘트 전송
```

### 3. AI 분석 실행

```
사용자가 "🤖 AI 분석" 버튼 클릭
    ↓
handle_interactive_components() → ai_analysis 액션 감지
    ↓
즉시 "🤖 AI 분석 시작 중..." 메시지 전송
    ↓
백그라운드 스레드 시작
    ↓
DB에서 Incident 정보 및 관련 알람 조회
    ↓
analyze_incident() 호출
    ↓
LangChain + Ollama로 AI 분석
    ↓
결과를 JSON으로 파싱
    ↓
Slack 스레드에 코멘트로 전송
```

---

## 환경 변수 설정

### 필수 환경 변수

#### Database
```bash
DB_HOST=mysql
DB_PORT=3306
DB_USER=observer
DB_PASSWORD=observer123
DB_NAME=observer
```

#### Slack
```bash
# Socket Mode (필수)
SLACK_APP_TOKEN=xapp-1-...

# 메시지 전송 (필수 - Webhook 또는 Bot Token 중 하나)
SLACK_BOT_TOKEN=xoxb-...
# 또는
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# 기본 채널
SLACK_CHANNEL=C0A4LAEF6P8
```

#### Grafana
```bash
GRAFANA_URL=http://host.docker.internal:32570
GRAFANA_USER=admin
GRAFANA_PASSWORD=admin
```

#### AI (Ollama)
```bash
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral
```

### Docker Compose 설정

`docker/mysql/docker-compose.yml`에서 환경 변수 설정:

```yaml
services:
  alert-receiver:
    environment:
      - DB_HOST=mysql
      - DB_USER=observer
      - DB_PASSWORD=observer123
      - SLACK_APP_TOKEN=${SLACK_APP_TOKEN}
      - SLACK_BOT_TOKEN=${SLACK_BOT_TOKEN}
      - GRAFANA_URL=http://host.docker.internal:32570
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## 주요 개념 정리

### Incident Key vs Incident ID

**Incident Key (사건 유형 키)**:
- 같은 유형의 알람을 그룹화
- `rule_uid|cluster|namespace|phase` → SHA256 → 16자리
- 예: `a7f3e4670f9d5f66`
- **용도**: 같은 문제의 반복 알람을 하나의 Incident로 관리

**Incident ID (에피소드 ID)**:
- 각 Incident 발생 시마다 새로 생성
- 형식: `INC-YYYYMMDDHHMMSS-{random_hex}`
- 예: `INC-20251230170000-abc123`
- **용도**: 특정 Incident 인스턴스 식별

### Status 상태 전이

```
active → acknowledged → resolved
  ↑           ↓
  └───────────┘ (재발생 시)
```

- `active`: 알람 발생, 처리 중
- `acknowledged`: 담당자가 확인
- `resolved`: 해결 완료

### 트랜잭션 관리

**원칙**: 함수 레벨에서 `commit` 하지 않음

**이유**: 여러 작업을 하나의 트랜잭션으로 묶기 위해

**예시**:
```python
conn.autocommit(False)
try:
    incident_id, is_new = find_or_create_incident(conn, ...)
    save_alert_to_db(conn, ...)
    conn.commit()
except:
    conn.rollback()
```

---

## 참고 자료

- **LangChain 문서**: https://python.langchain.com/
- **Ollama 문서**: https://ollama.ai/
- **Slack Block Kit**: https://api.slack.com/block-kit
- **Slack Socket Mode**: https://api.slack.com/apis/connections/socket
- **Grafana Alerting API**: https://grafana.com/docs/grafana/latest/alerting/manage-notifications/
- **Google SRE 책**: "Site Reliability Engineering"

---

## 문제 해결 가이드

### Slack 버튼이 동작하지 않을 때
1. `SLACK_APP_TOKEN` 확인
2. `SLACK_BOT_TOKEN` 확인
3. Socket Mode 클라이언트가 실행 중인지 확인
4. 로그 확인: `docker compose logs alert-receiver`

### AI 분석이 실행되지 않을 때
1. Ollama 서버가 실행 중인지 확인
2. `OLLAMA_BASE_URL` 확인
3. `OLLAMA_MODEL` 확인 (기본: `mistral`)
4. 로그 확인: `docker compose logs alert-receiver | grep AI`

### DB 연결 실패 시
1. MySQL 컨테이너가 실행 중인지 확인
2. 환경 변수 확인 (`DB_HOST`, `DB_USER`, `DB_PASSWORD`)
3. 네트워크 확인: `docker compose ps`

### Grafana Silence 생성 실패 시
1. `GRAFANA_URL` 확인
2. `GRAFANA_USER`, `GRAFANA_PASSWORD` 확인
3. Grafana API 접근 권한 확인
4. 로그 확인: `docker compose logs alert-receiver | grep Silence`

