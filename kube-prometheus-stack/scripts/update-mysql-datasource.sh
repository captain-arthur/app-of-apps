#!/bin/bash
# MySQL 데이터소스 URL 업데이트 스크립트

set -e

GRAFANA_URL="${GRAFANA_URL:-http://localhost:32195}"
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_PASSWORD:-olol1234}"

echo "🔧 MySQL 데이터소스 URL 업데이트 중..."
echo "Grafana URL: $GRAFANA_URL"
echo ""

# 데이터소스 정보 가져오기
DS_INFO=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/datasources/uid/mysql-observer")

if [ -z "$DS_INFO" ] || echo "$DS_INFO" | grep -q "Not Found"; then
    echo "❌ 데이터소스를 찾을 수 없습니다. 먼저 생성하세요."
    exit 1
fi

# 현재 URL 확인
CURRENT_URL=$(echo "$DS_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', ''))" 2>/dev/null)
echo "현재 URL: $CURRENT_URL"

# URL 업데이트
echo ""
echo "📝 URL을 host.docker.internal:3306으로 업데이트 중..."

RESPONSE=$(curl -s -X PUT -u "$GRAFANA_USER:$GRAFANA_PASSWORD" \
  -H "Content-Type: application/json" \
  -d "$(echo "$DS_INFO" | python3 -c "
import sys, json
d = json.load(sys.stdin)
d['url'] = 'host.docker.internal:3306'
d.pop('id', None)
d.pop('access', None)
d.pop('typeLogoUrl', None)
d.pop('basicAuth', None)
d.pop('basicAuthUser', None)
d.pop('withCredentials', None)
d.pop('isDefault', None)
print(json.dumps(d))
" 2>/dev/null)" \
  "$GRAFANA_URL/api/datasources/uid/mysql-observer")

if echo "$RESPONSE" | grep -q "message"; then
    echo "❌ 업데이트 실패:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

echo "✅ 업데이트 완료!"

# Health check
echo ""
echo "🏥 Health check 중..."
sleep 2
HEALTH=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" -X POST "$GRAFANA_URL/api/datasources/uid/mysql-observer/health" 2>&1)

if echo "$HEALTH" | grep -q "OK\|ok"; then
    echo "✅ 데이터소스 연결 성공!"
else
    echo "⚠️  Health check 결과:"
    echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
fi

