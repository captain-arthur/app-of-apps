# 개발 가이드

## 로컬 개발 환경 설정

### 1. 사전 요구사항

- Docker & Docker Compose
- Python 3.9+ (로컬 개발 시)
- MySQL 클라이언트 (선택)

### 2. 환경 변수 설정

`.env` 파일 생성 (선택):

```bash
DB_HOST=mysql
DB_PORT=3306
DB_USER=observer
DB_PASSWORD=observer123
DB_NAME=observer
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 3. Docker Compose 실행

```bash
cd docker/mysql
docker compose up -d --build
```

### 4. 서비스 확인

```bash
# Health check
curl http://localhost:8000/health

# 서비스 정보
curl http://localhost:8000/
```

## 프로젝트 구조

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
    └── test_webhook.sh              # 테스트 스크립트
```

## 로컬 개발 (Python 직접 실행)

### 1. 가상 환경 설정

```bash
cd docker/alert-receiver
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=observer
export DB_PASSWORD=observer123
export DB_NAME=observer
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 3. 서버 실행

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## 테스트

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
```

## 코드 구조

### 주요 함수

- `calculate_incident_key()`: Incident Key 계산
- `generate_incident_id()`: Incident ID 생성
- `extract_alert_info()`: Alert 정보 추출
- `find_or_create_incident()`: Open Incident 찾기 또는 생성
- `save_alert_to_db()`: Alert DB 저장
- `send_to_slack()`: Slack 알림 전송

### 트랜잭션 처리

전체 흐름이 하나의 트랜잭션으로 처리됩니다:

```python
conn.autocommit(False)
try:
    incident_id, is_new = find_or_create_incident(conn, ...)
    alert_id = save_alert_to_db(conn, ..., incident_id, ...)
    conn.commit()
except:
    conn.rollback()
    raise
```

## 디버깅

### 로그 확인

```bash
# Alert Receiver 로그
docker logs alert-receiver

# MySQL 로그
docker logs mysql-observer
```

### DB 직접 접속

```bash
docker exec -it mysql-observer mysql -u observer -pobserver123 observer
```

## 문제 해결

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

### 포트 충돌

`docker-compose.yml`에서 포트 변경:

```yaml
ports:
  - "8001:8000"  # 8000 대신 다른 포트 사용
```

