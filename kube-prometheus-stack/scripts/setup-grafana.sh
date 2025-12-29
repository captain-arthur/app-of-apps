#!/bin/bash
# Grafana Contact Points, Rules, Policies, Dashboards 설정 스크립트

set -e

# 기본값 설정
GRAFANA_URL="${GRAFANA_URL:-http://localhost:30080}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-olol1234}"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
ALERT_RECEIVER_URL="${ALERT_RECEIVER_URL:-http://alert-receiver:8000/webhook/grafana}"

# 스크립트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔧 Grafana 설정 시작..."
echo "Grafana URL: $GRAFANA_URL"
echo ""

# Grafana가 준비될 때까지 대기
echo "⏳ Grafana 준비 대기 중..."
for i in {1..30}; do
    if curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
        echo "✅ Grafana 준비 완료"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Grafana가 준비되지 않았습니다"
        exit 1
    fi
    sleep 2
done

# 1. Contact Points 생성
echo ""
echo "📡 Contact Points 생성 중..."

# Alert Receiver Webhook
curl -s -X POST \
  -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Alert Receiver API\",
    \"type\": \"webhook\",
    \"settings\": {
      \"url\": \"$ALERT_RECEIVER_URL\",
      \"httpMethod\": \"POST\"
    },
    \"uid\": \"alert-receiver-webhook\"
  }" \
  "$GRAFANA_URL/api/v1/provisioning/contact-points" > /dev/null

echo "✅ Alert Receiver Webhook 생성 완료"

# Slack Contact Point (Incoming Webhook 사용)
if [ -n "$SLACK_WEBHOOK_URL" ]; then
    curl -s -X POST \
      -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
      -H "Content-Type: application/json" \
      -d "{
        \"name\": \"Slack Alert Channel\",
        \"type\": \"slack\",
        \"settings\": {
          \"url\": \"$SLACK_WEBHOOK_URL\",
          \"recipient\": \"C0A4LAEF6P8\",
          \"text\": \"{{ template \\\"default.message\\\" . }}\",
          \"title\": \"{{ template \\\"default.title\\\" . }}\"
        },
        \"uid\": \"slack-receiver\"
      }" \
      "$GRAFANA_URL/api/v1/provisioning/contact-points" > /dev/null
    
    echo "✅ Slack Contact Point 생성 완료"
else
    echo "⚠️  SLACK_WEBHOOK_URL이 설정되지 않아 Slack Contact Point를 건너뜁니다"
fi

# 2. Notification Policy 생성
echo ""
echo "📋 Notification Policy 생성 중..."

curl -s -X PUT \
  -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
  -H "Content-Type: application/json" \
  -d "{
    \"receiver\": \"alert-receiver-webhook\",
    \"group_by\": [\"alertname\", \"severity\"],
    \"group_wait\": \"10s\",
    \"group_interval\": \"10s\",
    \"repeat_interval\": \"12h\",
    \"routes\": [
      {
        \"receiver\": \"alert-receiver-webhook\",
        \"continue\": true,
        \"matchers\": []
      }
    ]
  }" \
  "$GRAFANA_URL/api/v1/provisioning/policies" > /dev/null

echo "✅ Notification Policy 생성 완료"

# 3. Alert Rule 생성
echo ""
echo "📊 Alert Rule 생성 중..."

curl -s -X POST \
  -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"장애 알람 테스트\",
    \"condition\": \"A\",
    \"data\": [
      {
        \"refId\": \"A\",
        \"datasourceUid\": \"-100\",
        \"model\": {
          \"datasource\": {
            \"type\": \"__expr__\",
            \"uid\": \"-100\"
          },
          \"expression\": \"1 == 1\",
          \"type\": \"math\",
          \"refId\": \"A\"
        }
      }
    ],
    \"noDataState\": \"Alerting\",
    \"execErrState\": \"Alerting\",
    \"for\": \"0s\",
    \"annotations\": {
      \"description\": \"장애 알람 테스트용 알람입니다. 이 알람은 항상 트리거됩니다.\",
      \"summary\": \"장애 알람 테스트\"
    },
    \"labels\": {
      \"severity\": \"critical\",
      \"team\": \"devops\"
    },
    \"uid\": \"test-alert-rule\",
    \"ruleGroup\": \"Test Alert Group\",
    \"folderUID\": \"Alerting\",
    \"intervalSeconds\": 10
  }" \
  "$GRAFANA_URL/api/ruler/grafana/api/v1/rules/Alerting/test-alert-rule" > /dev/null

echo "✅ Alert Rule 생성 완료"

# 4. Dashboards 생성
echo ""
echo "📈 Dashboards 생성 중..."

# Incident Management Dashboard
if [ -f "$PROJECT_ROOT/dashboards/incident-management-dashboard.json" ]; then
    DASHBOARD_JSON=$(cat "$PROJECT_ROOT/dashboards/incident-management-dashboard.json")
    curl -s -X POST \
      -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
      -H "Content-Type: application/json" \
      -d "$DASHBOARD_JSON" \
      "$GRAFANA_URL/api/dashboards/db" > /dev/null
    
    echo "✅ Incident Management Dashboard 생성 완료"
else
    echo "⚠️  incident-management-dashboard.json을 찾을 수 없습니다"
fi

# Test Alert Dashboard
if [ -f "$PROJECT_ROOT/dashboards/test-alert-dashboard.json" ]; then
    DASHBOARD_JSON=$(cat "$PROJECT_ROOT/dashboards/test-alert-dashboard.json")
    curl -s -X POST \
      -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
      -H "Content-Type: application/json" \
      -d "$DASHBOARD_JSON" \
      "$GRAFANA_URL/api/dashboards/db" > /dev/null
    
    echo "✅ Test Alert Dashboard 생성 완료"
else
    echo "⚠️  test-alert-dashboard.json을 찾을 수 없습니다"
fi

echo ""
echo "✅ 모든 설정 완료!"
echo ""
echo "📊 Grafana 대시보드: $GRAFANA_URL"
echo "👤 사용자: $GRAFANA_USER"

