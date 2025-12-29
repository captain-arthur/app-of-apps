#!/bin/bash
# Slack Interactive Components 설정 자동화 스크립트

set -e

echo "🔧 Slack Interactive Components 설정"
echo ""

# 1. 환경 변수 확인
if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo "⚠️  SLACK_WEBHOOK_URL 환경 변수가 설정되지 않았습니다."
    echo "현재 Grafana에서 알람이 오고 있다면, Grafana의 Slack Contact Point에서 webhook URL을 확인하세요."
    echo ""
    read -p "Slack Webhook URL을 입력하세요: " SLACK_WEBHOOK_URL
    export SLACK_WEBHOOK_URL
fi

if [ -z "$SLACK_SIGNING_SECRET" ]; then
    echo ""
    echo "📋 Slack Signing Secret 설정이 필요합니다."
    echo ""
    echo "1. https://api.slack.com/apps 접속"
    echo "2. 알람이 오고 있는 Slack 앱 선택"
    echo "3. 'Interactivity & Shortcuts' 메뉴 클릭"
    echo "4. 'Interactivity' 토글을 ON으로 설정"
    echo "5. Request URL 입력:"
    
    # 로컬 IP 확인
    LOCAL_IP=$(ifconfig | grep "inet " | grep -v "127.0.0.1" | awk '{print $2}' | head -1)
    if [ -n "$LOCAL_IP" ]; then
        echo "   http://$LOCAL_IP:8000/slack/interactions"
    else
        echo "   http://YOUR_IP:8000/slack/interactions"
        echo "   또는 ngrok 사용: https://xxxx.ngrok-free.app/slack/interactions"
    fi
    
    echo "6. 'Signing Secret' 섹션에서 'Show' 클릭하여 Secret 복사"
    echo ""
    read -p "Slack Signing Secret을 입력하세요: " SLACK_SIGNING_SECRET
    export SLACK_SIGNING_SECRET
fi

# 2. .env 파일 생성
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
echo ""
echo "📝 .env 파일 생성: $ENV_FILE"
cat > "$ENV_FILE" << EOF
SLACK_WEBHOOK_URL=$SLACK_WEBHOOK_URL
SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET
EOF

echo "✅ .env 파일 생성 완료"
echo ""

# 3. 컨테이너 재시작
echo "🔄 컨테이너 재시작 중..."
cd "$(dirname "${BASH_SOURCE[0]}")/../mysql"
docker compose up -d --build alert-receiver

echo ""
echo "✅ 설정 완료!"
echo ""
echo "📋 다음 단계:"
echo "1. Grafana에서 알람 발생"
echo "2. Slack에서 Block Kit 카드 확인 (버튼 포함)"
echo "3. 버튼 클릭 테스트"
echo ""
echo "🔍 로그 확인:"
echo "   docker logs alert-receiver | tail -20"

