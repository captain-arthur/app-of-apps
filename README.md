# Grafana Alert → DB → Slack 기반 Incident Management

Grafana에서 발생하는 알람을 원본 그대로 DB에 저장하고, 이를 사건(Incident) 단위로 묶어 관리하며, 동시에 Slack으로 알람을 전달하는 운영 프로토타입입니다.

## 🏗️ 아키텍처

```
Grafana Alert (발생)
    ↓ (Webhook)
Alert Receiver API (FastAPI)
    ├─→ MySQL DB
    │   ├─→ grafana_alerts (원본 알람 저장)
    │   └─→ incidents (사건 관리)
    └─→ Slack Notification
```

## ✨ 주요 기능

- ✅ **Grafana 알람 원본 저장**: 모든 알람을 DB에 무조건 저장하여 운영 데이터로 축적
- ✅ **Incident 자동 분류**: Fingerprint 기반으로 동일 유형 알람을 자동으로 같은 Incident로 묶음
- ✅ **Slack 알림 전송**: 실시간 알람 알림
- ✅ **SRE 원칙 기반 대시보드**: Four Golden Signals, MTTR, Error Budget 등
- ✅ **동적 필터링**: cluster, namespace, service, severity, status 기반 필터링

## 🚀 빠른 시작

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

### 4. Grafana 설정

Grafana의 Alert Rule에서 Contact Point를 설정:

- **Type**: Webhook
- **URL**: `http://alert-receiver:8000/webhook/grafana` (Kubernetes 내부)
  또는 `http://localhost:8000/webhook/grafana` (로컬 테스트)

자세한 설정 방법은 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)를 참조하세요.

## 📁 프로젝트 구조

```
.
├── docker/                    # 로컬 개발 환경
│   ├── mysql/                # MySQL 데이터베이스
│   │   ├── docker-compose.yml
│   │   └── init/
│   │       └── 01-init-database.sql
│   └── alert-receiver/       # Alert Receiver API
│       ├── app.py
│       ├── Dockerfile
│       └── requirements.txt
├── kube-prometheus-stack/    # Kubernetes 배포 (Helm Chart)
│   ├── ol-values.yaml
│   ├── dashboards/
│   └── scripts/
├── argo-cd/                  # Argo CD 설정 (Helm Chart)
└── docs/                     # 문서
    ├── ARCHITECTURE.md
    ├── DATABASE.md
    ├── DEVELOPMENT.md
    └── DEPLOYMENT.md
```

## 📚 문서

- [아키텍처](docs/ARCHITECTURE.md) - 시스템 아키텍처 및 설계 철학
- [데이터베이스](docs/DATABASE.md) - DB 스키마 및 설계 개선 사항
- [개발 가이드](docs/DEVELOPMENT.md) - 로컬 개발 환경 설정
- [배포 가이드](docs/DEPLOYMENT.md) - Kubernetes 배포 방법
- [프로젝트 분석](docs/PROJECT_ANALYSIS.md) - 프로젝트 목적, 기여도, 향후 방향

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

## 🎯 핵심 설계 철학

- **Alert ≠ Incident**: Alert는 시스템 이벤트, Incident는 사람이 관리하는 상태 객체
- **Fingerprint 기반 자동 분류**: 동일 유형 알람은 자동으로 같은 Incident로 묶임
- **데이터 중심 운영**: 모든 알람을 저장하여 분석 및 개선 가능

## 🚀 향후 확장 아이디어

- [ ] Slack 버튼 → Ack / Resolve
- [ ] REST API로 Incident 상태 변경
- [ ] 노이즈 자동 판정
- [ ] AI 요약 (alerts → root cause 추천)
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
```

### Slack 전송 실패

- `SLACK_WEBHOOK_URL` 환경 변수 확인
- 웹훅 URL 유효성 확인
- 로그에서 오류 메시지 확인

## 📄 라이선스

이 프로젝트는 프로토타입입니다.
