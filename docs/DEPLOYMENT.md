# 배포 가이드

## Kubernetes 배포

### 1. 사전 요구사항

- Kubernetes 클러스터
- Helm 3.x
- kubectl

### 2. Grafana 설정

#### Contact Point 설정

Grafana의 Alerting > Contact points에서 다음 설정 추가:

- **Name**: Alert Receiver API
- **Type**: Webhook
- **URL**: `http://alert-receiver:8000/webhook/grafana` (Kubernetes 내부)
  또는 `http://host.docker.internal:8000/webhook/grafana` (호스트 Docker Compose)

#### API를 통한 설정

```bash
cd kube-prometheus-stack
bash scripts/setup-grafana.sh
```

환경 변수 설정:

```bash
export GRAFANA_URL="http://localhost:3000"  # Port-forward 사용 시
export GRAFANA_USER="admin"
export GRAFANA_PASSWORD="olol1234"
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export ALERT_RECEIVER_URL="http://host.docker.internal:8000/webhook/grafana"
```

### 3. MySQL Datasource 설정

Grafana에서 MySQL 데이터베이스를 Datasource로 추가:

- **Name**: MySQL Observer
- **Type**: MySQL
- **Host**: `host.docker.internal:3306` (호스트 Docker Compose)
- **Database**: `observer`
- **User**: `observer`
- **Password**: `observer123`

또는 API를 통한 설정:

```bash
cd kube-prometheus-stack
bash scripts/update-mysql-datasource.sh
```

### 4. Dashboard 설정

Incident Management Dashboard는 `setup-grafana.sh` 스크립트를 통해 자동으로 생성됩니다.

수동으로 생성하려면:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -u admin:olol1234 \
  http://localhost:3000/api/dashboards/db \
  -d @kube-prometheus-stack/dashboards/incident-management-dashboard.json
```

## Slack 웹훅 설정

### 방법 1: 환경 변수

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### 방법 2: Kubernetes Secret

```bash
kubectl create secret generic slack-webhook \
  --from-literal=url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL' \
  -n monitoring
```

### 방법 3: 로컬 파일 (개발용)

`kube-prometheus-stack/ol-values.local.yaml` 파일 생성:

```yaml
grafana:
  alerting:
    contactpoints:
      yaml:
        secret:
          contactPoints:
            - name: Slack Alert Channel
              receivers:
                - uid: slack-receiver
                  type: slack
                  settings:
                    url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
                    recipient: "C0A4LAEF6P8"  # Slack 채널 ID
```

**주의**: 이 파일은 `.gitignore`에 포함되어 있어 Git에 커밋되지 않습니다.

## Alert Rule 설정

### 테스트 Alert Rule

`setup-grafana.sh` 스크립트를 통해 자동으로 생성됩니다.

수동으로 생성하려면 Grafana UI에서:

1. Alerting > Alert rules > New alert rule
2. Query: `1 == 1` (항상 트리거)
3. Contact point: Alert Receiver API

## Notification Policy 설정

모든 알람을 Alert Receiver API로 전송하도록 설정:

1. Alerting > Notification policies
2. Default policy 수정
3. Contact point: Alert Receiver API

## 모니터링

### Grafana 접속

```bash
# Port-forward
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

# 또는 NodePort
kubectl get svc -n monitoring kube-prometheus-stack-grafana
# NodePort 확인 후 http://<node-ip>:<nodeport> 접속
```

### 로그 확인

```bash
# Alert Receiver 로그
kubectl logs -n monitoring deployment/alert-receiver

# Grafana 로그
kubectl logs -n monitoring deployment/kube-prometheus-stack-grafana
```

## 문제 해결

### Grafana에서 Alert Receiver API에 연결할 수 없는 경우

1. Alert Receiver 서비스가 실행 중인지 확인
2. URL이 올바른지 확인 (`http://host.docker.internal:8000/webhook/grafana`)
3. 네트워크 정책 확인

### MySQL Datasource 연결 실패

1. MySQL이 호스트에서 실행 중인지 확인
2. `host.docker.internal`이 올바르게 설정되었는지 확인
3. 방화벽 설정 확인

### Slack 알림이 전송되지 않는 경우

1. `SLACK_WEBHOOK_URL` 환경 변수 확인
2. 웹훅 URL 유효성 확인
3. Slack 채널 ID 확인 (`recipient` 필드)

