-- Observer 데이터베이스 생성 (이미 docker-compose에서 생성되지만 명시적으로 생성)
CREATE DATABASE IF NOT EXISTS observer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE observer;

-- 알람/사건 테이블 생성
CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(255) PRIMARY KEY COMMENT '사건별 고유 아이디',
    status ENUM('active', 'acknowledged', 'resolved', 'suppressed') NOT NULL DEFAULT 'active' COMMENT '현재상태',
    severity VARCHAR(50) COMMENT '알람 등급',
    phase VARCHAR(50) COMMENT '환경구분',
    cluster VARCHAR(255) COMMENT '클러스터 구분',
    namespace VARCHAR(255) COMMENT '네임스페이스 구분',
    service VARCHAR(255) COMMENT '서비스 구분',
    service_category VARCHAR(255) COMMENT '서비스 대분류',
    start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '알람 발생 시각',
    acknowledged_time DATETIME NULL COMMENT '담당자가 인지한 시각',
    resolved_time DATETIME NULL COMMENT '문제 해결 시각',
    action_taken TEXT COMMENT '담당자가 기록한 조치 내용',
    root_cause TEXT COMMENT '문제의 근본 원인',
    resolved_by VARCHAR(255) COMMENT '해결 담당자',
    is_noise BOOLEAN DEFAULT FALSE COMMENT '노이즈 여부',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '레코드 생성 시각',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '레코드 수정 시각',
    INDEX idx_status (status),
    INDEX idx_severity (severity),
    INDEX idx_cluster (cluster),
    INDEX idx_namespace (namespace),
    INDEX idx_service (service),
    INDEX idx_start_time (start_time),
    INDEX idx_is_noise (is_noise)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='알람/사건 관리 테이블';

