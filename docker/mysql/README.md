# MySQL Observer 데이터베이스

## 개요
알람/사건 관리를 위한 MySQL 데이터베이스입니다.  
스키마는 `init/01-init-database.sql` 파일로 관리됩니다.

## 사용 방법

### 시작 (DB 초기화 상태로 생성)
```bash
cd docker/mysql
docker compose up -d
```

### 중지 및 데이터 삭제
```bash
docker compose down -v
```
`-v` 옵션으로 볼륨을 삭제하여 모든 데이터가 초기화됩니다.

### 스키마 변경 후 재시작
1. `init/01-init-database.sql` 파일 수정
2. 컨테이너 중지 및 볼륨 삭제: `docker compose down -v`
3. 재시작: `docker compose up -d`

## 데이터베이스 정보

- **데이터베이스명**: observer
- **사용자명**: observer
- **비밀번호**: observer123
- **Root 비밀번호**: olol1234
- **포트**: 3306
- **타임존**: Asia/Seoul (KST)

## MySQL 접속

### 로컬 접속 (컨테이너 내부)
```bash
docker exec -it mysql-observer mysql -u observer -pobserver123 observer
```

또는 root 계정으로:
```bash
docker exec -it mysql-observer mysql -u root -polol1234 observer
```

### 원격 접속

**연결 정보:**
- **호스트**: `localhost` (로컬) 또는 `192.168.45.204` (같은 네트워크)
- **포트**: `3306`
- **데이터베이스**: `observer`
- **사용자명**: `observer` 또는 `root`
- **비밀번호**: `observer123` (observer 계정) 또는 `olol1234` (root 계정)

**연결 문자열 예시:**
```
mysql://observer:observer123@localhost:3306/observer
mysql://root:olol1234@localhost:3306/observer
```

**명령줄로 원격 접속:**
```bash
# observer 계정
mysql -h localhost -P 3306 -u observer -pobserver123 observer

# root 계정
mysql -h localhost -P 3306 -u root -polol1234 observer
```

**다양한 클라이언트 도구:**
- **MySQL Workbench**: MySQL 공식 GUI 도구
- **DBeaver**: 범용 DB 관리 도구
- **TablePlus**: macOS용 DB 클라이언트
- **DataGrip**: JetBrains의 DB IDE
- **phpMyAdmin**: 웹 기반 관리 도구

**주의사항:**
- 원격 접속을 허용하려면 방화벽에서 3306 포트가 열려있어야 합니다.
- 보안을 위해 프로덕션 환경에서는 외부 포트 노출을 제한하고, VPN이나 SSH 터널을 사용하는 것을 권장합니다.

## 스키마 관리

스키마는 `init/01-init-database.sql` 파일에서 관리됩니다.
- 이 파일은 컨테이너 최초 실행 시 자동으로 실행됩니다.
- 스키마를 변경하려면 파일을 수정한 후 `docker compose down -v && docker compose up -d`로 재시작하세요.

