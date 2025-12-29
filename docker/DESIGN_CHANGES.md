# 🔧 설계 수정 반영 완료

## ✅ 주요 변경사항

### 1. **suppressed 상태 제거**
- `incidents.status`에서 `suppressed` 제거
- 상태는 `active`, `acknowledged`, `resolved`만 사용

### 2. **incident_key와 incident_id 분리**

#### incident_key (유형 키, 고정)
- `rule_uid|cluster|namespace|service|phase` → SHA256 → 앞 16자
- 같은 서비스/환경 알람은 항상 같은 `incident_key`

#### incident_id (에피소드 ID, 매번 새로 생성)
- 형식: `INC-YYYYMMDDHHMMSS-{incident_key}`
- 예: `INC-20251229184530-68b1e881dd57a3b9`
- Open incident가 없을 때만 새로 생성

### 3. **silences 테이블 추가**
- Slack "무시" 기능을 위한 별도 테이블
- Incident 상태가 아닌 알림 정책
- `incident_key` 기반으로 silence 관리

### 4. **알람 처리 로직 변경**

#### 기존 로직
```python
# incident_id로 직접 조회
SELECT * FROM incidents WHERE incident_id = ?
```

#### 새로운 로직
```python
# 1. incident_key 계산
# 2. Open incident 조회 (status IN ('active','acknowledged'))
SELECT incident_id FROM incidents 
WHERE incident_key = ? 
  AND status IN ('active','acknowledged')
ORDER BY last_seen_at DESC LIMIT 1

# 3. 있으면 기존 사용, 없으면 새로 생성
```

### 5. **Slack 전송 로직 변경**

#### 기존
- 항상 Slack 전송

#### 새로운
```python
# Silence 체크
SELECT 1 FROM silences 
WHERE incident_key = ? 
  AND NOW() BETWEEN starts_at AND ends_at

# 있으면 → Slack 전송 ❌
# 없으면 → Slack 전송 ✅
```

**중요:** DB 저장과 Incident 업데이트는 silence 여부와 무관하게 항상 수행

## 📊 DB 스키마 변경

### incidents 테이블
- ✅ `incident_key` 컬럼 추가 (INDEX)
- ✅ `status` ENUM에서 `suppressed` 제거
- ✅ `idx_incident_key_status` 복합 인덱스 추가

### silences 테이블 (신규)
```sql
CREATE TABLE silences (
    silence_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    incident_key VARCHAR(64) NOT NULL,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    created_by VARCHAR(255),
    reason TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_incident_key (incident_key),
    INDEX idx_ends_at (ends_at),
    INDEX idx_active (incident_key, starts_at, ends_at)
);
```

## 🔄 처리 흐름

```
Grafana Alert
    ↓
1. grafana_alerts INSERT (항상)
    ↓
2. incident_key 계산
    ↓
3. Open Incident 조회
    ├─ 있으면 → 기존 사용 (업데이트)
    └─ 없으면 → 새로 생성
    ↓
4. incident_alert_links INSERT
    ↓
5. Silence 체크
    ├─ 있으면 → Slack 전송 ❌
    └─ 없으면 → Slack 전송 ✅
```

## 🎯 핵심 설계 철학

**Incident는 "운영 객체"**  
**Silence는 "알림 정책"**

- 사건은 `resolved` 전까지 유효
- 무시는 알림만 잠시 끔
- DB 저장은 항상 수행

## 📝 다음 단계

1. ✅ DB 스키마 수정 완료
2. ✅ 코드 로직 수정 완료
3. ⏳ 테스트 필요
4. ⏳ Silence 생성 API (향후 구현)

