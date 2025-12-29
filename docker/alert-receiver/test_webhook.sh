#!/bin/bash
# Grafana Webhook 테스트 스크립트

WEBHOOK_URL="${1:-http://localhost:8000/webhook/grafana}"

echo "🧪 Grafana Webhook 테스트 시작..."
echo "📡 Webhook URL: $WEBHOOK_URL"
echo ""

# Grafana webhook 형식의 테스트 payload
PAYLOAD='{
  "receiver": "test-receiver",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "장애 알람 테스트",
        "rule_uid": "test-alert-rule",
        "severity": "critical",
        "cluster": "prod-cluster",
        "namespace": "production",
        "service": "payment-api",
        "phase": "production",
        "job": "payment-api"
      },
      "annotations": {
        "summary": "장애 알람 테스트",
        "description": "장애 알람 테스트용 알람입니다. 이 알람은 항상 트리거됩니다."
      },
      "startsAt": "2024-01-01T00:00:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "http://grafana:3000/alerting/test"
    }
  ],
  "groupLabels": {
    "alertname": "장애 알람 테스트"
  },
  "commonLabels": {
    "alertname": "장애 알람 테스트",
    "severity": "critical"
  },
  "commonAnnotations": {
    "summary": "장애 알람 테스트"
  },
  "externalURL": "http://grafana:3000",
  "version": "1",
  "groupKey": "{}:{alertname=\"장애 알람 테스트\"}",
  "truncatedAlerts": 0
}'

echo "📤 테스트 알람 전송 중..."
echo ""

RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "$WEBHOOK_URL")

HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_CODE/d')

echo "📥 응답 코드: $HTTP_CODE"
echo "📄 응답 본문:"
echo "$BODY" | jq '.' 2>/dev/null || echo "$BODY"
echo ""

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ 테스트 성공!"
else
  echo "❌ 테스트 실패 (HTTP $HTTP_CODE)"
  exit 1
fi

