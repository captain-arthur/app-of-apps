# Grafana Alert Receiver

Grafana Alert → DB → Slack 기반 Incident 관리 프로토타입

## 기능

- Grafana Webhook 수신
- 알람 원본 DB 저장 (grafana_alerts)
- Incident 분류 및 관리 (incidents)
- Alert-Incident 연결 (incident_alert_links)
- Slack 알람 전송

## 환경 변수

`.env` 파일을 생성하거나 docker-compose.yml에서 환경 변수 설정:

```bash
DB_HOST=mysql
DB_PORT=3306
DB_USER=observer
DB_PASSWORD=observer123
DB_NAME=observer
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## 실행

```bash
cd docker/mysql
docker-compose up -d
```

## API 엔드포인트

- `POST /webhook/grafana` - Grafana webhook 수신
- `GET /health` - Health check
- `GET /` - 서비스 정보

## Grafana 설정

Grafana Alert Rule의 Contact Point에서 Webhook URL을 설정:

```
http://alert-receiver:8000/webhook/grafana
```

또는 로컬에서 테스트하는 경우:

```
http://localhost:8000/webhook/grafana
```

