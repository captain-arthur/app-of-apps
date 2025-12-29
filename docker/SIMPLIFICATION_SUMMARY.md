# ✅ 2개 테이블로 단순화 완료

## 변경사항 요약

### 제거된 테이블
- ❌ `incident_alert_links` - 제거됨
- ❌ `silences` - 제거됨 (이번 단순화 범위에서 제외)

### 최종 테이블 구조 (2개만)

#### 1. incidents (사건 테이블)
- `incident_id` VARCHAR(64) PK - 에피소드 ID
- `incident_key` VARCHAR(16) NOT NULL - 유형 키
- `status` ENUM('active','acknowledged','resolved')
- 기타 컬럼들...

#### 2. grafana_alerts (원본 알람 테이블)
- `alert_id` BIGINT PK AUTO_INCREMENT
- `incident_id` VARCHAR(64) NOT NULL FK → incidents.incident_id
- `incident_key` VARCHAR(16) NOT NULL (조회 편의/검증용)
- 기타 컬럼들...

## 처리 흐름

```
1. payload에서 incident_key 생성
   ↓
2. Open Incident 조회 (status IN ('active','acknowledged'))
   ├─ 있으면 → 기존 incident_id 사용
   └─ 없으면 → 새 incident 생성
   ↓
3. grafana_alerts INSERT
   - incident_id, incident_key 포함
   ↓
4. Slack 전송
```

## 핵심 변경점

### 이전 (3개 테이블)
- `grafana_alerts` 저장
- `incidents` 저장
- `incident_alert_links`에 연결 저장

### 현재 (2개 테이블)
- `grafana_alerts`에 `incident_id` FK 직접 저장
- `incidents` 저장
- 연결 테이블 불필요

## 완료 기준 (DoD) ✅

- ✅ 동일 `incident_key`로 unresolved 상태일 때 알람 반복 → `incidents` 1건만 유지, `alert_count`, `last_seen_at`만 증가
- ✅ `grafana_alerts`에는 알람 이벤트가 매번 저장됨
- ✅ `grafana_alerts.incident_id` → `incidents.incident_id` 연결이 항상 유지됨

