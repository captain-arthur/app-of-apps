# DB 설계 개선 완료 보고서

## 📋 개요

DB 설계 문제점을 스키마 설계와 코드 설계로 해결 완료했습니다.

**작업 일시**: 2025-12-30  
**작업 범위**: 동시성 문제, 트랜잭션 범위, 인덱스 최적화, 데이터 무결성, alert_count 불일치

---

## ✅ 완료된 작업

### 1. DB 스키마 개선

#### 1.1 인덱스 최적화
**파일**: `docker/mysql/init/01-init-database.sql`

**추가된 인덱스**:
```sql
CREATE INDEX idx_incident_key_status_last_seen 
ON incidents (incident_key, status, last_seen_at DESC);
```

**효과**:
- `WHERE incident_key = ? AND status IN (...) ORDER BY last_seen_at DESC` 쿼리 최적화
- `Using filesort` 제거, 인덱스 직접 활용
- 대량 데이터 처리 시 성능 향상

#### 1.2 트리거 추가 (데이터 무결성 및 alert_count 자동 관리)

**트리거 1: alert_count 자동 업데이트 (INSERT)**
```sql
CREATE TRIGGER trg_update_alert_count_on_insert
AFTER INSERT ON grafana_alerts
FOR EACH ROW
BEGIN
    UPDATE incidents
    SET alert_count = (
        SELECT COUNT(*) FROM grafana_alerts 
        WHERE incident_id = NEW.incident_id
    )
    WHERE incident_id = NEW.incident_id;
END;
```

**트리거 2: alert_count 자동 업데이트 (DELETE)**
```sql
CREATE TRIGGER trg_update_alert_count_on_delete
AFTER DELETE ON grafana_alerts
FOR EACH ROW
BEGIN
    UPDATE incidents
    SET alert_count = (
        SELECT COUNT(*) FROM grafana_alerts 
        WHERE incident_id = OLD.incident_id
    )
    WHERE incident_id = OLD.incident_id;
END;
```

**트리거 3: 데이터 무결성 체크 (중복 open incident 방지)**
```sql
CREATE TRIGGER trg_prevent_duplicate_open_incident
BEFORE INSERT ON incidents
FOR EACH ROW
BEGIN
    DECLARE open_count INT;
    
    SELECT COUNT(*) INTO open_count
    FROM incidents
    WHERE incident_key = NEW.incident_key
      AND status IN ('active', 'acknowledged')
      AND incident_id != NEW.incident_id;
    
    IF open_count > 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Duplicate open incident detected';
    END IF;
END;
```

**효과**:
- ✅ `alert_count` 자동 동기화 (수동 업데이트 불필요)
- ✅ 같은 `incident_key`에 여러 open incident 생성 방지
- ✅ 데이터 무결성 보장

---

### 2. 코드 개선

#### 2.1 동시성 문제 해결
**파일**: `docker/alert-receiver/app.py`  
**함수**: `find_or_create_incident()`

**변경 사항**:
```python
# 변경 전
SELECT incident_id FROM incidents 
WHERE incident_key = ? AND status IN (...)
ORDER BY last_seen_at DESC LIMIT 1

# 변경 후
SELECT incident_id FROM incidents 
WHERE incident_key = ? AND status IN (...)
ORDER BY last_seen_at DESC LIMIT 1
FOR UPDATE  -- Row Lock 추가
```

**효과**:
- ✅ Race Condition 제거
- ✅ 동시 요청 시 하나만 처리
- ✅ 데이터 중복 방지

#### 2.2 트랜잭션 범위 확대
**파일**: `docker/alert-receiver/app.py`  
**함수**: `grafana_webhook()`, `find_or_create_incident()`, `save_alert_to_db()`

**변경 사항**:
- `find_or_create_incident()`: `conn.commit()` 제거
- `save_alert_to_db()`: `conn.commit()` 제거
- `grafana_webhook()`: 전체 흐름을 하나의 트랜잭션으로 처리, 마지막에 `conn.commit()`

**효과**:
- ✅ 원자성 보장 (All or Nothing)
- ✅ 중간 실패 시 롤백으로 데이터 불일치 방지
- ✅ orphaned incident 방지

---

## 🧪 테스트 결과

### 1. 인덱스 최적화 확인
```sql
EXPLAIN SELECT incident_id, alert_count 
FROM incidents 
WHERE incident_key = 'test-key' 
  AND status IN ('active', 'acknowledged')
ORDER BY last_seen_at DESC LIMIT 1;
```

**결과**:
- ✅ 복합 인덱스 `idx_incident_key_status_last_seen` 사용 확인
- ✅ `Using filesort` 제거
- ✅ 쿼리 성능 향상

### 2. 트리거 동작 확인
```sql
SHOW TRIGGERS;
```

**결과**:
- ✅ `trg_update_alert_count_on_insert` 생성 확인
- ✅ `trg_update_alert_count_on_delete` 생성 확인
- ✅ `trg_prevent_duplicate_open_incident` 생성 확인

### 3. alert_count 자동 동기화 확인
```sql
SELECT i.incident_id, i.alert_count, COUNT(ga.alert_id) as actual_count
FROM incidents i
LEFT JOIN grafana_alerts ga ON i.incident_id = ga.incident_id
GROUP BY i.incident_id, i.alert_count;
```

**결과**:
- ✅ `alert_count`와 실제 COUNT 일치 확인
- ✅ 트리거가 자동으로 업데이트하는 것 확인

### 4. 동시성 테스트
**테스트 방법**: 같은 `incident_key`로 5개 요청 동시 전송

**결과**:
- ✅ 모든 요청이 성공적으로 처리됨
- ✅ 같은 `incident_key`에 하나의 open incident만 생성됨
- ✅ `alert_count`가 정확히 업데이트됨

### 5. 트랜잭션 테스트
**테스트 방법**: 정상 케이스 및 에러 케이스 테스트

**결과**:
- ✅ 정상 케이스: 모든 데이터가 정상적으로 저장됨
- ✅ 에러 케이스: 롤백으로 데이터 불일치 방지 확인

---

## 📊 개선 전후 비교

| 항목 | 개선 전 | 개선 후 |
|------|---------|---------|
| **동시성 문제** | Race Condition 가능 | SELECT FOR UPDATE로 해결 |
| **트랜잭션 범위** | 각 함수별 commit | 전체 흐름 하나의 트랜잭션 |
| **인덱스** | 단일 인덱스만 | 복합 인덱스 추가 |
| **alert_count** | 수동 업데이트 | 트리거 자동 업데이트 |
| **데이터 무결성** | 애플리케이션 레벨만 | 트리거 + 코드 이중 체크 |
| **쿼리 성능** | Using filesort | 인덱스 직접 활용 |

---

## 🎯 해결된 문제점

### ✅ 해결 완료
1. **동시성 문제 (Race Condition)**
   - SELECT FOR UPDATE로 Row Lock
   - 트리거로 중복 체크

2. **트랜잭션 범위 문제**
   - 전체 흐름을 하나의 트랜잭션으로
   - 에러 시 롤백 처리

3. **인덱스 최적화**
   - 복합 인덱스 추가
   - 쿼리 성능 향상

4. **데이터 무결성**
   - 트리거로 중복 open incident 방지
   - 애플리케이션 레벨 이중 체크

5. **alert_count 불일치**
   - 트리거로 자동 동기화
   - 수동 업데이트 불필요

---

## 📝 변경된 파일

### DB 스키마
- `docker/mysql/init/01-init-database.sql`
  - 복합 인덱스 추가
  - 트리거 3개 추가

### 코드
- `docker/alert-receiver/app.py`
  - `find_or_create_incident()`: SELECT FOR UPDATE 추가, commit 제거
  - `save_alert_to_db()`: commit 제거
  - `grafana_webhook()`: 트랜잭션 범위 확대, commit/rollback 처리

---

## 🚀 향후 개선 사항 (선택)

1. **성능 모니터링**
   - 쿼리 실행 시간 측정
   - 인덱스 사용률 모니터링

2. **트리거 최적화**
   - 대량 데이터 처리 시 성능 확인
   - 필요 시 배치 처리로 변경

3. **로깅 강화**
   - 트랜잭션 실패 시 상세 로그
   - 동시성 충돌 감지 로그

---

## ✅ 완료 확인

- [x] DB 스키마 수정 (인덱스, 트리거)
- [x] 코드 수정 (SELECT FOR UPDATE, 트랜잭션 범위)
- [x] 테스트 완료 (동시성, 트랜잭션, 인덱스)
- [x] 결과 보고서 작성

---

**작성자**: Auto (Cursor AI)  
**작성일**: 2025-12-30

