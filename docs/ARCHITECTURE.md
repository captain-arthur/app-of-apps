# 시스템 아키텍처

## 개요

Grafana Alert → DB → Slack 기반 Incident Management 시스템의 아키텍처 및 설계 철학을 설명합니다.

## 핵심 아키텍처

```
Grafana Alert (발생)
    ↓ (Webhook)
Alert Receiver API (FastAPI)
    ├─→ MySQL DB
    │   ├─→ grafana_alerts (원본 알람 저장)
    │   └─→ incidents (사건 관리)
    └─→ Slack Notification
```

## 설계 철학

### Alert ≠ Incident

- **Alert**: 시스템이 발생시키는 이벤트 (중복/폭주 가능)
- **Incident**: 사람이 관리하는 상태 객체 (Active → Acknowledged → Resolved)

따라서 DB 테이블도 분리합니다:
- `grafana_alerts`: 모든 알람 이벤트 저장 (무조건 INSERT)
- `incidents`: 사건 단위 상태 관리 (UPSERT)

### Fingerprint 기반 자동 분류

동일 유형 알람은 자동으로 같은 Incident로 묶입니다.

**Incident Key 계산**:
```python
incident_key = SHA256(
    rule_uid + "|" +
    cluster + "|" +
    namespace + "|" +
    service + "|" +
    phase
)[:16]
```

**Incident ID 생성**:
```
INC-{YYYYMMDDHHMMSS}-{incident_key}
```

예: `INC-20251229184530-68b1e881dd57a3b9`

### 데이터 중심 운영

- 모든 알람을 DB에 저장하여 운영 데이터로 축적
- 장기 보관 및 분석 가능
- MTTR, Error Budget 등 SRE 지표 계산 가능

## 처리 흐름

### 1. 알람 수신

```
Grafana Alert 발생
    ↓
Webhook → Alert Receiver API
    ↓
Payload 파싱 및 정보 추출
```

### 2. Incident 분류

```
Alert 정보 추출
    ↓
Incident Key 계산
    ↓
Open Incident 조회 (status IN ('active', 'acknowledged'))
    ├─ 있으면 → 기존 Incident 사용
    └─ 없으면 → 새 Incident 생성
```

### 3. 데이터 저장

```
트랜잭션 시작
    ↓
grafana_alerts INSERT (원본 저장)
    ↓
incidents UPDATE 또는 INSERT
    ↓
트랜잭션 커밋
```

### 4. 알림 전송

```
Slack Webhook 전송
    ├─ Incident ID
    ├─ Alert Count
    ├─ Severity
    └─ 상세 정보
```

## 데이터베이스 스키마

### grafana_alerts (원본 알람 테이블)

- **역할**: Grafana Webhook payload를 변형 없이 저장
- **특징**: 중복/폭주 허용, 운영의 "팩트 로그"
- **주요 컬럼**:
  - `alert_id`: PK
  - `incident_id`: FK → incidents.incident_id
  - `incident_key`: 조회 편의/검증용
  - `raw_payload`: 원본 JSON 전체

### incidents (사건 관리 테이블)

- **역할**: 사람이 관리하는 사건 단위 상태 저장
- **특징**: 알람 여러 개 → 사건 1개
- **주요 컬럼**:
  - `incident_id`: PK (에피소드 ID)
  - `incident_key`: 유형 키 (INDEX)
  - `status`: active / acknowledged / resolved
  - `alert_count`: 연결된 알람 개수 (트리거로 자동 업데이트)

## 동시성 처리

### 문제점

같은 `incident_key`로 동시에 알람이 수신되면 여러 open incident가 생성될 수 있음.

### 해결 방법

1. **SELECT FOR UPDATE**: Row Lock으로 동시성 문제 해결
2. **트리거**: 중복 open incident 방지
3. **트랜잭션**: 전체 흐름을 하나의 트랜잭션으로 처리

## 성능 최적화

### 인덱스

- `idx_incident_key_status_last_seen`: 복합 인덱스
  - `WHERE incident_key = ? AND status IN (...) ORDER BY last_seen_at DESC` 쿼리 최적화

### 트리거

- `trg_update_alert_count_on_insert`: INSERT 시 alert_count 자동 업데이트
- `trg_update_alert_count_on_delete`: DELETE 시 alert_count 자동 업데이트
- `trg_prevent_duplicate_open_incident`: 중복 open incident 방지

## 확장성

### 현재 구조

- 단일 MySQL 인스턴스
- 단일 Alert Receiver API

### 향후 확장 가능성

- MySQL 복제 (Master-Slave)
- Alert Receiver API 수평 확장
- Redis 캐싱
- 메시지 큐 (RabbitMQ, Kafka)

