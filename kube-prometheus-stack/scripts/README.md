# Grafana 설정 스크립트

## 개요

이 스크립트는 Grafana의 Contact Points, Notification Policies, Alert Rules, Dashboards를 API를 통해 생성합니다.

## 사용법

### 기본 사용

```bash
cd kube-prometheus-stack
bash scripts/setup-grafana.sh
```

### 환경 변수 설정

```bash
export GRAFANA_URL="http://localhost:32195"  # Grafana URL
export GRAFANA_USER="admin"                   # Grafana 사용자명
export GRAFANA_PASSWORD="olol1234"           # Grafana 비밀번호
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."  # Slack 웹훅 URL (선택)
export ALERT_RECEIVER_URL="http://alert-receiver:8000/webhook/grafana"  # Alert Receiver URL

bash scripts/setup-grafana.sh
```

### Kubernetes에서 실행

```bash
# NodePort 확인
kubectl get svc -n monitoring kube-prometheus-stack-grafana -o jsonpath='{.spec.ports[?(@.port==80)].nodePort}'

# 스크립트 실행
GRAFANA_URL="http://localhost:<NODEPORT>" \
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..." \
bash scripts/setup-grafana.sh
```

## 생성되는 리소스

1. **Contact Points**
   - Alert Receiver API (Webhook)
   - Slack Alert Channel (Slack)

2. **Notification Policy**
   - 모든 알람을 Alert Receiver API로 전송

3. **Alert Rule**
   - Test Alert Rule (항상 트리거되는 테스트 알람)

4. **Dashboards**
   - Incident Management Dashboard
   - Test Alert Dashboard

## 주의사항

- Grafana가 완전히 시작될 때까지 대기합니다 (최대 60초)
- Contact Points는 중복 생성 시 오류가 발생할 수 있습니다
- Dashboards는 중복 생성 시 업데이트됩니다

