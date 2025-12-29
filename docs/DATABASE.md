# 데이터베이스 설계

## 개요

MySQL 기반 Incident Management 데이터베이스의 스키마 및 설계 개선 사항을 설명합니다.

## 스키마 구조

### grafana_alerts (원본 알람 테이블)

**역할**: Grafana Webhook으로 들어온 알람 payload를 변형 없이 저장

**주요 컬럼**:
- `alert_id` BIGINT PK AUTO_INCREMENT
- `incident_id` VARCHAR(64) NOT NULL FK → incidents.incident_id
- `incident_key` VARCHAR(16) NOT NULL
- `received_at` DATETIME
- `state` VARCHAR(32) (firing / resolved)
- `rule_uid` VARCHAR(255)
- `alertname` VARCHAR(255)
- `message` TEXT
- `labels` JSON
- `annotations` JSON
- `raw_payload` JSON

**인덱스**:
- `idx_incident_id` (incident_id)
- `idx_incident_key_received_at` (incident_key, received_at)
- `idx_received_at` (received_at)

### incidents (사건 관리 테이블)

**역할**: 사람이 관리하는 사건 단위 상태 저장

**주요 컬럼**:
- `incident_id` VARCHAR(64) PK (에피소드 ID)
- `incident_key` VARCHAR(16) NOT NULL (유형 키)
- `status` ENUM('active', 'acknowledged', 'resolved')
- `severity` VARCHAR(50)
- `phase` VARCHAR(50)
- `cluster` VARCHAR(255)
- `namespace` VARCHAR(255)
- `service` VARCHAR(255)
- `service_category` VARCHAR(255)
- `start_time` DATETIME
- `first_seen_at` DATETIME
- `last_seen_at` DATETIME
- `alert_count` INT (트리거로 자동 업데이트)
- `acknowledged_time` DATETIME
- `resolved_time` DATETIME
- `action_taken` TEXT
- `root_cause` TEXT
- `resolved_by` VARCHAR(255)
- `is_noise` BOOLEAN

**인덱스**:
- `idx_incident_key` (incident_key)
- `idx_status` (status)
- `idx_last_seen_at` (last_seen_at)
- `idx_cluster_namespace_service` (cluster, namespace, service)
- `idx_service_category` (service_category)
- `idx_incident_key_status_last_seen` (incident_key, status, last_seen_at DESC) - **성능 최적화**

## 트리거

### 1. alert_count 자동 업데이트 (INSERT)

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

### 2. alert_count 자동 업데이트 (DELETE)

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

### 3. 중복 open incident 방지

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

## 설계 개선 사항

### 1. 동시성 문제 해결

**문제**: 같은 `incident_key`로 동시에 알람 수신 시 여러 open incident 생성 가능

**해결**:
- SELECT FOR UPDATE로 Row Lock
- 트리거로 중복 체크

### 2. 트랜잭션 범위 확대

**문제**: 각 함수별 commit으로 인한 데이터 불일치 가능

**해결**: 전체 흐름을 하나의 트랜잭션으로 처리

### 3. 인덱스 최적화

**추가**: 복합 인덱스 `idx_incident_key_status_last_seen`
- `WHERE incident_key = ? AND status IN (...) ORDER BY last_seen_at DESC` 쿼리 최적화

### 4. alert_count 자동 동기화

**문제**: 수동 업데이트로 인한 불일치 가능

**해결**: 트리거로 자동 업데이트

## 데이터베이스 접속

### 로컬 접속 (컨테이너 내부)

```bash
docker exec -it mysql-observer mysql -u observer -pobserver123 observer
```

### 원격 접속

**연결 정보**:
- 호스트: `localhost` (로컬) 또는 `192.168.45.204` (같은 네트워크)
- 포트: `3306`
- 데이터베이스: `observer`
- 사용자명: `observer` 또는 `root`
- 비밀번호: `observer123` (observer 계정) 또는 `olol1234` (root 계정)

**연결 문자열**:
```
mysql://observer:observer123@localhost:3306/observer
```

## 스키마 변경 방법

1. `docker/mysql/init/01-init-database.sql` 파일 수정
2. 컨테이너 중지 및 볼륨 삭제: `docker compose down -v`
3. 재시작: `docker compose up -d`

## 참고 문서

- [DB 설계 개선 보고서](../DB_IMPROVEMENT_REPORT.md) - 상세한 개선 사항 및 테스트 결과

# DB 설계 문제점 분석 및 개선 방안

## 🔍 발견된 주요 문제점

### 1. 🚨 동시성 문제 (Race Condition) - **가장 심각**

#### 문제 상황
```python
# find_or_create_incident 함수
1. SELECT incident_id FROM incidents 
   WHERE incident_key = ? AND status IN ('active', 'acknowledged')
   → 없음

2. INSERT INTO incidents ... (새 incident 생성)
```

**Race Condition 시나리오:**
```
시간 | Thread 1                    | Thread 2
-----|----------------------------|----------------------------
T1   | SELECT → 없음              |
T2   |                            | SELECT → 없음 (T1이 INSERT 전)
T3   | INSERT (INC-001)           |
T4   |                            | INSERT (INC-002) ← 중복!
```

#### 영향
- ✅ **비즈니스 규칙 위반**: "같은 incident_key에 하나의 open incident만 존재해야 함"
- ✅ **데이터 중복**: 동일 유형 알람이 여러 incident로 분산
- ✅ **alert_count 불일치**: 각 incident의 alert_count가 실제보다 적음

#### 해결 방안
1. **SELECT FOR UPDATE 사용** (Row Lock)
   ```sql
   SELECT incident_id FROM incidents 
   WHERE incident_key = ? AND status IN ('active', 'acknowledged')
   FOR UPDATE
   ORDER BY last_seen_at DESC LIMIT 1
   ```

2. **UNIQUE 제약 조건 추가**
   ```sql
   CREATE UNIQUE INDEX idx_incident_key_status 
   ON incidents (incident_key, status) 
   WHERE status IN ('active', 'acknowledged');
   ```
   ⚠️ MySQL은 부분 유니크 인덱스를 지원하지 않으므로 애플리케이션 레벨에서 처리 필요

3. **트랜잭션 범위 확대**
   - `find_or_create_incident`와 `save_alert_to_db`를 하나의 트랜잭션으로

---

### 2. 🚨 트랜잭션 범위 문제

#### 문제 상황
```python
# 현재 코드
incident_id, is_new = find_or_create_incident(conn, ...)  # commit
alert_id = save_alert_to_db(conn, ..., incident_id, ...)  # commit
```

**문제 시나리오:**
```
1. find_or_create_incident 성공 → commit
2. save_alert_to_db 실패 → rollback
   → incident는 생성되었는데 alert는 없음 (orphaned incident)
```

#### 영향
- ✅ **데이터 불일치**: incident는 있는데 연결된 alert 없음
- ✅ **FK 제약 위반 가능성**: grafana_alerts.incident_id가 존재하지 않는 incident 참조

#### 해결 방안
```python
# 전체를 하나의 트랜잭션으로
try:
    incident_id, is_new = find_or_create_incident(conn, ...)
    alert_id = save_alert_to_db(conn, ..., incident_id, ...)
    conn.commit()
except:
    conn.rollback()
    raise
```

---

### 3. ⚠️ 인덱스 최적화 부족

#### 문제 상황
```sql
-- 현재 쿼리
SELECT incident_id FROM incidents 
WHERE incident_key = ? 
  AND status IN ('active', 'acknowledged')
ORDER BY last_seen_at DESC
LIMIT 1
```

**현재 인덱스:**
- `idx_incident_key` (incident_key만)
- `idx_status` (status만)

**문제:**
- `status IN (...)` 조건이 인덱스를 활용하지 못함
- `ORDER BY last_seen_at`도 인덱스 없음

#### 해결 방안
```sql
-- 복합 인덱스 추가
CREATE INDEX idx_incident_key_status_last_seen 
ON incidents (incident_key, status, last_seen_at DESC);
```

---

### 4. ⚠️ 데이터 무결성 제약 부족

#### 문제 상황
- `incident_key`에 UNIQUE 제약 없음
- 같은 `incident_key`에 여러 open incident 생성 가능
- 비즈니스 규칙: "같은 incident_key에 하나의 open incident만"

#### 해결 방안
1. **애플리케이션 레벨 체크** (MySQL은 부분 유니크 인덱스 미지원)
   ```python
   # INSERT 전에 다시 한번 체크
   SELECT FOR UPDATE ... 
   # 없으면 INSERT
   ```

2. **트리거 사용** (복잡하지만 가능)
   ```sql
   CREATE TRIGGER check_single_open_incident
   BEFORE INSERT ON incidents
   FOR EACH ROW
   BEGIN
     IF EXISTS (
       SELECT 1 FROM incidents 
       WHERE incident_key = NEW.incident_key 
         AND status IN ('active', 'acknowledged')
     ) THEN
       SIGNAL SQLSTATE '45000' 
       SET MESSAGE_TEXT = 'Open incident already exists';
     END IF;
   END;
   ```

---

### 5. ⚠️ alert_count 불일치 가능성

#### 문제 상황
- `incidents.alert_count`는 수동 업데이트
- 실제 COUNT는 `SELECT COUNT(*) FROM grafana_alerts WHERE incident_id = ?`
- 트랜잭션 실패 시 불일치 가능

#### 해결 방안
1. **계산 컬럼 사용** (MySQL 5.7+)
   ```sql
   ALTER TABLE incidents 
   ADD COLUMN alert_count_calculated INT AS (
     (SELECT COUNT(*) FROM grafana_alerts 
      WHERE incident_id = incidents.incident_id)
   ) STORED;
   ```

2. **정기 동기화 작업**
   ```sql
   UPDATE incidents i
   SET alert_count = (
     SELECT COUNT(*) FROM grafana_alerts 
     WHERE incident_id = i.incident_id
   );
   ```

---

## 📋 개선 우선순위

### 🔴 긴급 (즉시 수정 필요)
1. **동시성 문제 해결**
   - SELECT FOR UPDATE 사용
   - 트랜잭션 범위 확대

2. **트랜잭션 범위 확대**
   - 전체 흐름을 하나의 트랜잭션으로

### 🟡 중요 (단기 개선)
3. **인덱스 최적화**
   - 복합 인덱스 추가

4. **데이터 무결성 강화**
   - 애플리케이션 레벨 체크 강화

### 🟢 개선 (중기 개선)
5. **alert_count 불일치 해결**
   - 계산 컬럼 또는 정기 동기화

---

## 🔧 구체적 개선 방안

### 방안 1: SELECT FOR UPDATE + 트랜잭션 확대

```python
def find_or_create_incident(conn, incident_key: str, alert_info: Dict[str, Any]) -> tuple[str, bool]:
    with conn.cursor() as cursor:
        # Row Lock으로 동시성 문제 해결
        cursor.execute("""
            SELECT incident_id, alert_count 
            FROM incidents 
            WHERE incident_key = %s 
              AND status IN ('active', 'acknowledged')
            ORDER BY last_seen_at DESC
            LIMIT 1
            FOR UPDATE  -- Row Lock 추가
        """, (incident_key,))
        existing = cursor.fetchone()
        
        if existing:
            # 기존 사용
            ...
        else:
            # 신규 생성
            ...
        # commit은 호출자에서 처리
```

### 방안 2: 복합 인덱스 추가

```sql
-- 기존 인덱스 유지하면서 복합 인덱스 추가
CREATE INDEX idx_incident_key_status_last_seen 
ON incidents (incident_key, status, last_seen_at DESC);
```

### 방안 3: 트랜잭션 범위 확대

```python
@app.post("/webhook/grafana")
async def grafana_webhook(request: Request):
    conn = get_db_connection()
    try:
        # 전체를 하나의 트랜잭션으로
        for alert in alerts:
            incident_id, is_new = find_or_create_incident(conn, ...)  # commit 제거
            alert_id = save_alert_to_db(conn, ..., incident_id, ...)  # commit 제거
            ...
        conn.commit()  # 마지막에 한번만
    except:
        conn.rollback()
        raise
    finally:
        conn.close()
```

---

## 📊 예상 개선 효과

### 동시성 문제 해결
- ✅ Race Condition 제거
- ✅ 데이터 중복 방지
- ✅ 비즈니스 규칙 준수

### 성능 개선
- ✅ 쿼리 속도 향상 (복합 인덱스)
- ✅ 대량 데이터 처리 가능

### 데이터 정합성
- ✅ 트랜잭션으로 원자성 보장
- ✅ alert_count 불일치 방지

---

**작성일**: 2025-12-30


---

## 설계 문제점 분석

## 🔍 발견된 주요 문제점

### 1. 🚨 동시성 문제 (Race Condition) - **가장 심각**

#### 문제 상황
```python
# find_or_create_incident 함수
1. SELECT incident_id FROM incidents 
   WHERE incident_key = ? AND status IN ('active', 'acknowledged')
   → 없음

2. INSERT INTO incidents ... (새 incident 생성)
```

**Race Condition 시나리오:**
```
시간 | Thread 1                    | Thread 2
-----|----------------------------|----------------------------
T1   | SELECT → 없음              |
T2   |                            | SELECT → 없음 (T1이 INSERT 전)
T3   | INSERT (INC-001)           |
T4   |                            | INSERT (INC-002) ← 중복!
```

#### 영향
- ✅ **비즈니스 규칙 위반**: "같은 incident_key에 하나의 open incident만 존재해야 함"
- ✅ **데이터 중복**: 동일 유형 알람이 여러 incident로 분산
- ✅ **alert_count 불일치**: 각 incident의 alert_count가 실제보다 적음

#### 해결 방안
1. **SELECT FOR UPDATE 사용** (Row Lock)
   ```sql
   SELECT incident_id FROM incidents 
   WHERE incident_key = ? AND status IN ('active', 'acknowledged')
   FOR UPDATE
   ORDER BY last_seen_at DESC LIMIT 1
   ```

2. **UNIQUE 제약 조건 추가**
   ```sql
   CREATE UNIQUE INDEX idx_incident_key_status 
   ON incidents (incident_key, status) 
   WHERE status IN ('active', 'acknowledged');
   ```
   ⚠️ MySQL은 부분 유니크 인덱스를 지원하지 않으므로 애플리케이션 레벨에서 처리 필요

3. **트랜잭션 범위 확대**
   - `find_or_create_incident`와 `save_alert_to_db`를 하나의 트랜잭션으로

---

### 2. 🚨 트랜잭션 범위 문제

#### 문제 상황
```python
# 현재 코드
incident_id, is_new = find_or_create_incident(conn, ...)  # commit
alert_id = save_alert_to_db(conn, ..., incident_id, ...)  # commit
```

**문제 시나리오:**
```
1. find_or_create_incident 성공 → commit
2. save_alert_to_db 실패 → rollback
   → incident는 생성되었는데 alert는 없음 (orphaned incident)
```

#### 영향
- ✅ **데이터 불일치**: incident는 있는데 연결된 alert 없음
- ✅ **FK 제약 위반 가능성**: grafana_alerts.incident_id가 존재하지 않는 incident 참조

#### 해결 방안
```python
# 전체를 하나의 트랜잭션으로
try:
    incident_id, is_new = find_or_create_incident(conn, ...)
    alert_id = save_alert_to_db(conn, ..., incident_id, ...)
    conn.commit()
except:
    conn.rollback()
    raise
```

---

### 3. ⚠️ 인덱스 최적화 부족

#### 문제 상황
```sql
-- 현재 쿼리
SELECT incident_id FROM incidents 
WHERE incident_key = ? 
  AND status IN ('active', 'acknowledged')
ORDER BY last_seen_at DESC
LIMIT 1
```

**현재 인덱스:**
- `idx_incident_key` (incident_key만)
- `idx_status` (status만)

**문제:**
- `status IN (...)` 조건이 인덱스를 활용하지 못함
- `ORDER BY last_seen_at`도 인덱스 없음

#### 해결 방안
```sql
-- 복합 인덱스 추가
CREATE INDEX idx_incident_key_status_last_seen 
ON incidents (incident_key, status, last_seen_at DESC);
```

---

### 4. ⚠️ 데이터 무결성 제약 부족

#### 문제 상황
- `incident_key`에 UNIQUE 제약 없음
- 같은 `incident_key`에 여러 open incident 생성 가능
- 비즈니스 규칙: "같은 incident_key에 하나의 open incident만"

#### 해결 방안
1. **애플리케이션 레벨 체크** (MySQL은 부분 유니크 인덱스 미지원)
   ```python
   # INSERT 전에 다시 한번 체크
   SELECT FOR UPDATE ... 
   # 없으면 INSERT
   ```

2. **트리거 사용** (복잡하지만 가능)
   ```sql
   CREATE TRIGGER check_single_open_incident
   BEFORE INSERT ON incidents
   FOR EACH ROW
   BEGIN
     IF EXISTS (
       SELECT 1 FROM incidents 
       WHERE incident_key = NEW.incident_key 
         AND status IN ('active', 'acknowledged')
     ) THEN
       SIGNAL SQLSTATE '45000' 
       SET MESSAGE_TEXT = 'Open incident already exists';
     END IF;
   END;
   ```

---

### 5. ⚠️ alert_count 불일치 가능성

#### 문제 상황
- `incidents.alert_count`는 수동 업데이트
- 실제 COUNT는 `SELECT COUNT(*) FROM grafana_alerts WHERE incident_id = ?`
- 트랜잭션 실패 시 불일치 가능

#### 해결 방안
1. **계산 컬럼 사용** (MySQL 5.7+)
   ```sql
   ALTER TABLE incidents 
   ADD COLUMN alert_count_calculated INT AS (
     (SELECT COUNT(*) FROM grafana_alerts 
      WHERE incident_id = incidents.incident_id)
   ) STORED;
   ```

2. **정기 동기화 작업**
   ```sql
   UPDATE incidents i
   SET alert_count = (
     SELECT COUNT(*) FROM grafana_alerts 
     WHERE incident_id = i.incident_id
   );
   ```

---

## 📋 개선 우선순위

### 🔴 긴급 (즉시 수정 필요)
1. **동시성 문제 해결**
   - SELECT FOR UPDATE 사용
   - 트랜잭션 범위 확대

2. **트랜잭션 범위 확대**
   - 전체 흐름을 하나의 트랜잭션으로

### 🟡 중요 (단기 개선)
3. **인덱스 최적화**
   - 복합 인덱스 추가

4. **데이터 무결성 강화**
   - 애플리케이션 레벨 체크 강화

### 🟢 개선 (중기 개선)
5. **alert_count 불일치 해결**
   - 계산 컬럼 또는 정기 동기화

---

## 🔧 구체적 개선 방안

### 방안 1: SELECT FOR UPDATE + 트랜잭션 확대

```python
def find_or_create_incident(conn, incident_key: str, alert_info: Dict[str, Any]) -> tuple[str, bool]:
    with conn.cursor() as cursor:
        # Row Lock으로 동시성 문제 해결
        cursor.execute("""
            SELECT incident_id, alert_count 
            FROM incidents 
            WHERE incident_key = %s 
              AND status IN ('active', 'acknowledged')
            ORDER BY last_seen_at DESC
            LIMIT 1
            FOR UPDATE  -- Row Lock 추가
        """, (incident_key,))
        existing = cursor.fetchone()
        
        if existing:
            # 기존 사용
            ...
        else:
            # 신규 생성
            ...
        # commit은 호출자에서 처리
```

### 방안 2: 복합 인덱스 추가

```sql
-- 기존 인덱스 유지하면서 복합 인덱스 추가
CREATE INDEX idx_incident_key_status_last_seen 
ON incidents (incident_key, status, last_seen_at DESC);
```

### 방안 3: 트랜잭션 범위 확대

```python
@app.post("/webhook/grafana")
async def grafana_webhook(request: Request):
    conn = get_db_connection()
    try:
        # 전체를 하나의 트랜잭션으로
        for alert in alerts:
            incident_id, is_new = find_or_create_incident(conn, ...)  # commit 제거
            alert_id = save_alert_to_db(conn, ..., incident_id, ...)  # commit 제거
            ...
        conn.commit()  # 마지막에 한번만
    except:
        conn.rollback()
        raise
    finally:
        conn.close()
```

---

## 📊 예상 개선 효과

### 동시성 문제 해결
- ✅ Race Condition 제거
- ✅ 데이터 중복 방지
- ✅ 비즈니스 규칙 준수

### 성능 개선
- ✅ 쿼리 속도 향상 (복합 인덱스)
- ✅ 대량 데이터 처리 가능

### 데이터 정합성
- ✅ 트랜잭션으로 원자성 보장
- ✅ alert_count 불일치 방지

---

**작성일**: 2025-12-30

