# Slack 웹훅 URL 설정 가이드

GitHub Push Protection을 피하기 위해 Slack 웹훅 URL은 코드 저장소에 포함하지 않습니다.

## 설정 방법

### 방법 1: Helm values에서 직접 설정 (개발/테스트용)

`ol-values.yaml` 파일의 `grafana.alerting.contactpoints.yaml.secret.contactPoints[0].receivers[0].settings.url` 필드에 직접 웹훅 URL을 입력하세요.

```yaml
grafana:
  alerting:
    contactpoints.yaml:
      secret:
        apiVersion: 1
        contactPoints:
          - orgId: 1
            name: Slack Alert Channel
            receivers:
              - uid: slack-receiver
                type: slack
                settings:
                  url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### 방법 2: Kubernetes Secret 사용 (프로덕션 권장)

1. Kubernetes Secret 생성:

```bash
kubectl create secret generic grafana-slack-webhook \
  --from-literal=url='https://hooks.slack.com/services/YOUR/WEBHOOK/URL' \
  -n monitoring
```

2. Helm values에서 Secret 참조:

`ol-values.yaml`에 다음 설정을 추가하거나 수정:

```yaml
grafana:
  extraSecretMounts:
    - name: slack-webhook-secret
      secretName: grafana-slack-webhook
      defaultMode: 0440
      mountPath: /etc/grafana/secrets/slack-webhook
      readOnly: true
```

또는 Grafana의 환경 변수로 주입:

```yaml
grafana:
  env:
    SLACK_WEBHOOK_URL:
      valueFrom:
        secretKeyRef:
          name: grafana-slack-webhook
          key: url
```

## 현재 웹훅 URL

현재 사용 중인 Slack 웹훅 URL은 로컬에서만 관리하거나 별도의 Secret 관리 시스템을 사용하세요.

**주의**: 이 파일은 Git에 커밋하지 마세요. 웹훅 URL이 포함되어 있으면 GitHub Push Protection에 의해 차단됩니다.

