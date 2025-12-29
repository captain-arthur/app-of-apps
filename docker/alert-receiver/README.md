# Alert Receiver API

Grafana Alert를 수신하여 DB에 저장하고 Slack으로 전송하는 FastAPI 서비스입니다.

## 빠른 시작

```bash
# Docker Compose로 실행
cd ../mysql
docker compose up -d

# 또는 로컬에서 직접 실행
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

## API 엔드포인트

- `POST /webhook/grafana` - Grafana webhook 수신
- `GET /health` - Health check
- `GET /` - 서비스 정보

## 테스트

```bash
bash test_webhook.sh http://localhost:8000/webhook/grafana
```

자세한 내용은 [개발 가이드](../../docs/DEVELOPMENT.md)를 참조하세요.
