# Grafana Alert → DB → Slack 기반 Incident 관리 프로토타입

## 📋 개요

Grafana에서 발생하는 알람을 원본 그대로 DB에 저장하고, 이를 사건(Incident) 단위로 묶어 관리하며, 동시에 Slack으로 알람을 전달하는 운영 프로토타입입니다.

## 🏗️ 아키텍처

```
Grafana Alert (Webhook)
        │
        ▼
 Alert Receiver API (FastAPI)
        │
        ├─ grafana_alerts  ← 원본 알람 저장 (무조건 insert)
        │
        ├─ Incident 분류 로직 (fingerprint 계산)
        │
        ├─ incidents       ← 사건 단위 upsert
        │
        ├─ incident_alert_links ← 알람 ↔ 사건 연결
        │
        └─ Slack Webhook 전송
```

## 📊 DB 스키마

### 1. grafana_alerts (원본 알람 테이블)
- Grafana에서 들어오는 알람 payload를 변형 없이 저장
- 중복/폭주 허용
- 운영의 "팩트 로그"

### 2. incidents (사건 관리 테이블)
- 사람이 관리하는 사건 단위 상태 저장
- 알람 여러 개 → 사건 1개
- status: active / acknowledged / resolved / suppressed

### 3. incident_alert_links (연결 테이블)
- 어떤 알람이 어떤 사건에 묶였는지 추적
- 감사(audit) 및 재분류 가능성 확보

## 🔑 Incident 분류 로직 (Fingerprint)

```python
incident_id = hash(
  rule_uid +
  cluster +
  namespace +
  service +
  phase
)
```

동일 서비스/환경에서 반복 발생하는 알람은 같은 incident로 묶입니다.

## 🚀 실행 방법

### 1. 환경 변수 설정

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### 2. Docker Compose 실행

```bash
cd docker/mysql
docker compose up -d --build
```

### 3. 서비스 확인

```bash
# Health check
curl http://localhost:8000/health

# 서비스 정보
curl http://localhost:8000/
```

## 🧪 테스트

### Webhook 테스트

```bash
cd docker/alert-receiver
bash test_webhook.sh http://localhost:8000/webhook/grafana
```

### DB 확인

```bash
# 알람 확인
docker exec mysql-observer mysql -uobserver -pobserver123 observer \
  -e "SELECT * FROM grafana_alerts ORDER BY alert_id DESC LIMIT 5;"

# Incident 확인
docker exec mysql-observer mysql -uobserver -pobserver123 observer \
  -e "SELECT * FROM incidents ORDER BY created_at DESC LIMIT 5;"

# 연결 확인
docker exec mysql-observer mysql -uobserver -pobserver123 observer \
  -e "SELECT * FROM incident_alert_links ORDER BY linked_at DESC LIMIT 5;"
```

## 📡 Grafana 설정

### Contact Point 추가

Grafana의 Alerting > Contact points에서 다음 설정 추가:

- **Name**: Alert Receiver API
- **Type**: Webhook
- **URL**: `http://alert-receiver:8000/webhook/grafana` (Kubernetes 내부)
  또는 `http://localhost:8000/webhook/grafana` (로컬 테스트)

### Notification Policy 설정

모든 알람을 Alert Receiver API로 전송하도록 설정합니다.

## ✅ 테스트 결과

### 성공 케이스

1. ✅ Grafana webhook 수신 성공
2. ✅ 알람 원본 DB 저장 (grafana_alerts)
3. ✅ Incident 생성/업데이트 (incidents)
4. ✅ Alert-Incident 연결 (incident_alert_links)
5. ✅ Slack 알람 전송
6. ✅ 동일 알람 반복 발생 시 incident 증가하지 않고 alert_count만 증가

### 테스트 데이터

```
Alerts: 2개
Incidents: 1개
Links: 2개
```

- 첫 번째 알람: 신규 Incident 생성 (alert_count=1)
- 두 번째 알람: 기존 Incident 업데이트 (alert_count=2)

## 📁 파일 구조

```
docker/
├── mysql/
│   ├── docker-compose.yml          # MySQL + Alert Receiver 서비스
│   └── init/
│       └── 01-init-database.sql     # DB 스키마
└── alert-receiver/
    ├── app.py                       # FastAPI 서버
    ├── Dockerfile                   # Docker 이미지
    ├── requirements.txt             # Python 의존성
    ├── test_webhook.sh              # 테스트 스크립트
    └── README.md                    # 상세 문서
```

## 🔧 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| DB_HOST | mysql | MySQL 호스트 |
| DB_PORT | 3306 | MySQL 포트 |
| DB_USER | observer | MySQL 사용자 |
| DB_PASSWORD | observer123 | MySQL 비밀번호 |
| DB_NAME | observer | 데이터베이스 이름 |
| SLACK_WEBHOOK_URL | - | Slack 웹훅 URL (필수) |

## 📝 API 엔드포인트

- `POST /webhook/grafana` - Grafana webhook 수신
- `GET /health` - Health check
- `GET /` - 서비스 정보

## 🎯 완료 기준 (Definition of Done)

✅ **모두 완료됨**

- [x] Grafana 테스트 알람 발생 시 grafana_alerts에 원본 저장됨
- [x] incidents에 사건 1개 생성/갱신됨
- [x] incident_alert_links에 연결 기록 남음
- [x] Slack으로 메시지 전송됨
- [x] 동일 알람 반복 발생 시 incidents는 증가하지 않고 alert_count만 증가

## 🚀 향후 확장 아이디어

- [ ] Slack 버튼 → Ack / Resolve
- [ ] Incident 기반 Grafana Dashboard
- [ ] 노이즈 자동 판정
- [ ] AI 요약 (alerts → root cause 추천)
- [ ] REST API로 Incident 상태 변경
- [ ] 웹 UI 대시보드

## 📞 문제 해결

### 서비스가 시작되지 않는 경우

```bash
# 로그 확인
docker logs alert-receiver
docker logs mysql-observer

# 재시작
docker compose restart
```

### DB 연결 실패

```bash
# MySQL 상태 확인
docker exec mysql-observer mysqladmin ping -h localhost -u root -polol1234

# 네트워크 확인
docker network inspect mysql_observer-network
```

### Slack 전송 실패

- `SLACK_WEBHOOK_URL` 환경 변수 확인
- 웹훅 URL 유효성 확인
- 로그에서 오류 메시지 확인

