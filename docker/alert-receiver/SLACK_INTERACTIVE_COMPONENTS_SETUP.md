# Slack Interactive Components 설정 상세 가이드

## 목적
Slack 메시지의 버튼(Ack, Resolve, Mute)이 작동하도록 Interactive Components를 활성화합니다.

---

## 1단계: Slack 앱 관리 페이지 접속

1. 웹 브라우저에서 다음 URL 접속:
   ```
   https://api.slack.com/apps
   ```

2. Slack 계정으로 로그인 (필요시)

---

## 2단계: 기존 앱 선택

현재 알람이 오고 있는 Slack 앱을 선택합니다.

**알람이 오고 있는 앱을 찾는 방법:**
- Slack 채널에서 알람 메시지 확인
- 메시지 하단에 "Added by [앱 이름]" 표시 확인
- 또는 "Incoming Webhook"을 사용 중이라면 해당 앱 선택

**앱이 없다면:**
- "Create New App" 클릭
- "From scratch" 선택
- 앱 이름 입력 (예: "Incident Management")
- 워크스페이스 선택
- "Create App" 클릭

---

## 3단계: Interactivity & Shortcuts 활성화

### 3.1 메뉴 접근
1. 왼쪽 사이드바에서 **"Interactivity & Shortcuts"** 클릭
   - 또는 "Features" 섹션에서 찾기

### 3.2 Interactivity 활성화
1. **"Interactivity"** 섹션 찾기
2. **"Interactivity"** 토글을 **ON**으로 변경
   - 기본값은 OFF입니다

### 3.3 Request URL 설정
1. **"Request URL"** 입력 필드에 다음 URL 입력:
   ```
   http://192.168.45.204:8000/slack/interactions
   ```
   - 또는 로컬 테스트용 ngrok URL:
   ```
   https://xxxx-xx-xx-xx-xx.ngrok-free.app/slack/interactions
   ```

2. **"Save Changes"** 버튼 클릭

**⚠️ 중요:**
- URL이 접근 가능해야 합니다
- 로컬 개발 환경이라면 ngrok 사용 권장
- 서버에 배포했다면 실제 서버 IP/도메인 사용

---

## 4단계: Signing Secret 복사

### 4.1 Signing Secret 확인
1. 같은 페이지("Interactivity & Shortcuts")에서 아래로 스크롤
2. **"Signing Secret"** 섹션 찾기

### 4.2 Secret 복사
1. **"Show"** 버튼 클릭
2. 표시된 Secret 복사 (예: `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`)
   - 이 값은 나중에 다시 볼 수 없으므로 안전한 곳에 저장

---

## 5단계: 환경 변수 설정

### 방법 1: 직접 export (임시)
```bash
export SLACK_SIGNING_SECRET="복사한_signing_secret"
docker compose -f docker/mysql/docker-compose.yml up -d alert-receiver
```

### 방법 2: .env 파일 생성 (영구)
```bash
cd /Users/hooni/Documents/github/ol-devops-api-test
echo "SLACK_SIGNING_SECRET=복사한_signing_secret" >> .env
docker compose -f docker/mysql/docker-compose.yml up -d alert-receiver
```

### 방법 3: docker-compose.yml 직접 수정
```yaml
environment:
  SLACK_SIGNING_SECRET: "복사한_signing_secret"
```

---

## 6단계: 컨테이너 재시작

```bash
cd /Users/hooni/Documents/github/ol-devops-api-test
docker compose -f docker/mysql/docker-compose.yml up -d alert-receiver
```

---

## 7단계: 테스트

### 7.1 알람 발생
1. Grafana에서 알람 발생
2. Slack에서 Block Kit 카드 확인
3. 버튼 5개가 표시되는지 확인:
   - 👀 Ack
   - ✅ Resolve
   - 🔕 Mute 30m
   - 🔕 Mute 2h
   - 🔕 Mute 24h

### 7.2 버튼 클릭 테스트
1. **Ack 버튼** 클릭
   - DB 확인: `incidents.status = 'acknowledged'`
   - Slack 스레드에 댓글 확인

2. **Resolve 버튼** 클릭
   - DB 확인: `incidents.status = 'resolved'`
   - Slack 스레드에 댓글 확인

3. **Mute 버튼** 클릭
   - DB 확인: `silences` 테이블에 레코드 추가
   - 이후 알람 발생 시 Slack 전송 스킵 확인

---

## 로컬 개발 환경: ngrok 설정 (선택사항)

로컬에서 테스트하려면 ngrok을 사용하여 외부 접근 가능한 URL을 생성합니다.

### ngrok 설치 (macOS)
```bash
brew install ngrok
```

### ngrok 실행
```bash
ngrok http 8000
```

### 출력 예시
```
Forwarding  https://xxxx-xx-xx-xx-xx.ngrok-free.app -> http://localhost:8000
```

### Slack Request URL에 입력
```
https://xxxx-xx-xx-xx-xx.ngrok-free.app/slack/interactions
```

**⚠️ 주의:**
- ngrok을 종료하면 URL이 변경됩니다
- 무료 버전은 URL이 매번 변경됩니다
- 프로덕션 환경에서는 고정 도메인 사용 권장

---

## 문제 해결

### 버튼이 보이지 않는 경우
1. ✅ Interactive Components가 ON인지 확인
2. ✅ Request URL이 올바르게 설정되었는지 확인
3. ✅ URL이 접근 가능한지 확인 (curl 테스트)
4. ✅ Slack 앱이 올바른 워크스페이스에 설치되었는지 확인

### 버튼 클릭 시 에러가 발생하는 경우
1. ✅ SLACK_SIGNING_SECRET 환경 변수 확인
   ```bash
   docker exec alert-receiver printenv | grep SLACK_SIGNING_SECRET
   ```

2. ✅ 서명 검증 로그 확인
   ```bash
   docker logs alert-receiver | grep -i "signature\|서명"
   ```

3. ✅ Request URL이 올바른지 확인
   - Slack 앱 설정과 실제 서버 URL 일치 확인

### 서명 검증 실패
- Signing Secret이 올바르게 설정되었는지 확인
- Slack 앱의 Signing Secret과 환경 변수가 일치하는지 확인

---

## 확인 명령어

### 환경 변수 확인
```bash
docker exec alert-receiver printenv | grep SLACK
```

### 엔드포인트 확인
```bash
curl http://localhost:8000/
# 응답에 "slack_interactions": "/slack/interactions" 포함 확인
```

### 로그 확인
```bash
docker logs alert-receiver | tail -20
```

---

## 완료 체크리스트

- [ ] Slack 앱 관리 페이지 접속
- [ ] 기존 앱 선택 (또는 새 앱 생성)
- [ ] Interactivity & Shortcuts 메뉴 접근
- [ ] Interactivity 토글 ON
- [ ] Request URL 설정
- [ ] Signing Secret 복사
- [ ] 환경 변수 설정
- [ ] 컨테이너 재시작
- [ ] 알람 발생 테스트
- [ ] 버튼 클릭 테스트
- [ ] DB 업데이트 확인

---

## 추가 정보

- [Slack Interactive Components 공식 문서](https://api.slack.com/interactivity)
- [Slack Block Kit 가이드](https://api.slack.com/block-kit)
- [Slack Signing Secret 설명](https://api.slack.com/authentication/verifying-requests-from-slack)

