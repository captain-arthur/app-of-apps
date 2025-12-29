#!/bin/bash
# 테스트용 데이터 생성 스크립트

WEBHOOK_URL="${1:-http://localhost:8000/webhook/grafana}"

echo "📊 테스트 데이터 생성 시작..."
echo ""

# 다양한 서비스/환경 알람 생성
services=("payment-api" "user-api" "order-api" "notification-api")
clusters=("prod-cluster" "staging-cluster")
namespaces=("production" "staging")
severities=("critical" "warning" "warning" "info")

for i in {1..20}; do
    service_idx=$((RANDOM % ${#services[@]}))
    cluster_idx=$((RANDOM % ${#clusters[@]}))
    namespace_idx=$((RANDOM % ${#namespaces[@]}))
    severity_idx=$((RANDOM % ${#severities[@]}))
    
    service=${services[$service_idx]}
    cluster=${clusters[$cluster_idx]}
    namespace=${namespaces[$namespace_idx]}
    severity=${severities[$severity_idx]}
    
    # 약간의 랜덤 딜레이
    sleep 0.5
    
    PAYLOAD=$(cat <<EOF
{
  "receiver": "test-receiver",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "CPU High Load",
        "rule_uid": "cpu-high-load-rule",
        "severity": "${severity}",
        "cluster": "${cluster}",
        "namespace": "${namespace}",
        "service": "${service}",
        "phase": "${namespace}",
        "job": "${service}"
      },
      "annotations": {
        "summary": "CPU High Load - ${service}",
        "description": "CPU usage is above 80% for ${service} in ${namespace}"
      }
    }
  ]
}
EOF
)
    
    echo "📤 알람 전송: ${service} (${cluster}/${namespace}) - ${severity}"
    curl -s -X POST \
      -H "Content-Type: application/json" \
      -d "$PAYLOAD" \
      "$WEBHOOK_URL" > /dev/null
    
    # 같은 서비스 알람을 여러 번 보내서 중복 처리 확인
    if [ $((i % 3)) -eq 0 ]; then
        sleep 1
        echo "🔄 중복 알람 전송: ${service}"
        curl -s -X POST \
          -H "Content-Type: application/json" \
          -d "$PAYLOAD" \
          "$WEBHOOK_URL" > /dev/null
    fi
done

echo ""
echo "✅ 테스트 데이터 생성 완료!"
echo ""
echo "📊 통계 확인:"
echo "docker exec mysql-observer mysql -uobserver -pobserver123 observer -e \"SELECT 'Alerts' as table_name, COUNT(*) as count FROM grafana_alerts UNION ALL SELECT 'Incidents', COUNT(*) FROM incidents;\""

