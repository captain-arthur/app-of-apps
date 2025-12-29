# MySQL Observer 데이터베이스

Incident Management를 위한 MySQL 데이터베이스입니다.

## 빠른 시작

```bash
docker compose up -d
```

## 데이터베이스 정보

- **데이터베이스명**: observer
- **사용자명**: observer
- **비밀번호**: observer123
- **Root 비밀번호**: olol1234
- **포트**: 3306

## 접속

```bash
# 컨테이너 내부
docker exec -it mysql-observer mysql -u observer -pobserver123 observer

# 원격 접속
mysql -h localhost -P 3306 -u observer -pobserver123 observer
```

## 스키마 변경

1. `init/01-init-database.sql` 파일 수정
2. `docker compose down -v` (볼륨 삭제)
3. `docker compose up -d` (재시작)

자세한 내용은 [데이터베이스 문서](../../docs/DATABASE.md)를 참조하세요.
