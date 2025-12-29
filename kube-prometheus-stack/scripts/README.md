# Grafana 설정 스크립트

Grafana의 Contact Points, Notification Policies, Alert Rules, Dashboards를 API를 통해 생성하는 스크립트입니다.

## 사용법

```bash
export GRAFANA_URL="http://localhost:3000"
export GRAFANA_USER="admin"
export GRAFANA_PASSWORD="olol1234"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export ALERT_RECEIVER_URL="http://host.docker.internal:8000/webhook/grafana"

bash setup-grafana.sh
```

자세한 내용은 [배포 가이드](../../docs/DEPLOYMENT.md)를 참조하세요.
