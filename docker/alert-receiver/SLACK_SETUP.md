# Slack Interactive Components 설정 가이드

## 현재 상황
- ✅ Slack webhook은 이미 설정되어 있음 (알람이 오고 있음)
- ⏳ Interactive Components URL 설정 필요
- ⏳ Signing Secret 설정 필요

## 설정 단계

### 1. Slack 앱 관리 페이지 접속
https://api.slack.com/apps

### 2. 기존 앱 선택
알람이 오고 있는 Slack 앱을 선택합니다.

### 3. Interactivity & Shortcuts 활성화
1. 왼쪽 메뉴에서 **"Interactivity & Shortcuts"** 클릭
2. **"Interactivity"** 토글을 **ON**으로 설정
3. **Request URL** 입력:
   - **로컬 테스트**: ngrok 사용 (아래 참고)
   - **서버 배포**: `http://YOUR_SERVER_IP:8000/slack/interactions`
4. **"Save Changes"** 클릭

### 4. Signing Secret 복사
- 같은 페이지에서 **"Signing Secret"** 섹션 확인
- **"Show"** 클릭하여 Secret 복사
- 이 값을 환경 변수로 설정해야 합니다

### 5. 로컬 테스트용 ngrok 설정 (선택사항)

```bash
# ngrok 설치 (macOS)
brew install ngrok

# ngrok 실행 (8000 포트 포워딩)
ngrok http 8000

# 출력된 URL 예시: https://xxxx-xx-xx-xx-xx.ngrok-free.app
# 이 URL을 Slack Request URL에 입력:
# https://xxxx-xx-xx-xx-xx.ngrok-free.app/slack/interactions
```

### 6. 환경 변수 설정

#### 방법 1: 직접 export
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
export SLACK_SIGNING_SECRET="your_signing_secret_here"
```

#### 방법 2: .env 파일 생성
```bash
cd /Users/hooni/Documents/github/ol-devops-api-test
cat > .env << EOF
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_SIGNING_SECRET=your_signing_secret_here
EOF
```

### 7. 컨테이너 재시작
```bash
cd /Users/hooni/Documents/github/ol-devops-api-test
docker compose -f docker/mysql/docker-compose.yml up -d --build alert-receiver
```

### 8. 테스트
1. Grafana에서 알람 발생
2. Slack에서 Block Kit 카드 확인 (버튼 포함)
3. 버튼 클릭 테스트:
   - 👀 Ack 버튼
   - ✅ Resolve 버튼
   - 🔕 Mute 버튼들

## 확인 사항

### 환경 변수 확인
```bash
docker exec alert-receiver printenv | grep SLACK
```

### 로그 확인
```bash
docker logs alert-receiver | tail -20
```

### 엔드포인트 확인
```bash
curl http://localhost:8000/
# 응답에 /slack/interactions 엔드포인트가 포함되어야 함
```

## 문제 해결

### 버튼이 보이지 않는 경우
- Slack 앱의 "Interactivity & Shortcuts"가 활성화되어 있는지 확인
- Request URL이 올바르게 설정되어 있는지 확인
- ngrok을 사용하는 경우 ngrok이 실행 중인지 확인

### 버튼 클릭 시 에러가 발생하는 경우
- Signing Secret이 올바르게 설정되어 있는지 확인
- 로그에서 에러 메시지 확인: `docker logs alert-receiver`

### Slack 메시지가 오지 않는 경우
- SLACK_WEBHOOK_URL 환경 변수 확인
- Grafana webhook 설정 확인

