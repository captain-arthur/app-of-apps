-- Observer 데이터베이스 생성 (이미 docker-compose에서 생성되지만 명시적으로 생성)
CREATE DATABASE IF NOT EXISTS observer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE observer;

-- 1. grafana_alerts 테이블: 원본 알람 저장 (무조건 insert)
CREATE TABLE IF NOT EXISTS grafana_alerts (
    alert_id BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '알람 고유 ID',
    incident_id VARCHAR(64) NOT NULL COMMENT '사건 ID (FK → incidents.incident_id)',
    incident_key VARCHAR(16) NOT NULL COMMENT '유형 키 (조회 편의/검증용)',
    received_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '수신 시각',
    state VARCHAR(32) NULL COMMENT 'firing / resolved',
    rule_uid VARCHAR(255) NULL COMMENT 'Grafana Rule UID',
    alertname VARCHAR(255) NULL COMMENT '알람 이름',
    message TEXT NULL COMMENT 'Slack에 전송되는 본문',
    labels JSON NULL COMMENT '알람 라벨 (JSON)',
    annotations JSON NULL COMMENT '알람 어노테이션 (JSON)',
    raw_payload JSON NULL COMMENT '원본 Grafana payload 전체',
    INDEX idx_incident_id (incident_id),
    INDEX idx_incident_key_received_at (incident_key, received_at),
    INDEX idx_received_at (received_at),
    FOREIGN KEY (incident_id) REFERENCES incidents(incident_id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Grafana 원본 알람 저장';

-- 2. incidents 테이블: 사건 관리 (사람이 관리하는 상태 객체)
CREATE TABLE IF NOT EXISTS incidents (
    incident_id VARCHAR(64) PRIMARY KEY COMMENT '에피소드 ID (INC-{timestamp}-{incident_key})',
    incident_key VARCHAR(16) NOT NULL COMMENT '유형 키 (rule_uid|cluster|namespace|service|phase 해시)',
    status ENUM('active', 'acknowledged', 'resolved') NOT NULL DEFAULT 'active' COMMENT '현재상태',
    severity VARCHAR(50) NULL COMMENT '알람 등급',
    phase VARCHAR(50) NULL COMMENT '환경구분',
    cluster VARCHAR(255) NULL COMMENT '클러스터 구분',
    namespace VARCHAR(255) NULL COMMENT '네임스페이스 구분',
    service VARCHAR(255) NULL COMMENT '서비스 구분',
    service_category VARCHAR(255) NULL COMMENT '서비스 대분류',
    start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '알람 발생 시각 (최초 발생 시각)',
    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '최초 발생 시각 (start_time과 동일)',
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '최근 발생 시각',
    alert_count INT NOT NULL DEFAULT 0 COMMENT '연결된 알람 개수',
    acknowledged_time DATETIME NULL COMMENT '담당자가 인지한 시각',
    resolved_time DATETIME NULL COMMENT '문제 해결 시각',
    action_taken TEXT NULL COMMENT '담당자가 기록한 조치 내용',
    root_cause TEXT NULL COMMENT '문제의 근본 원인',
    resolved_by VARCHAR(255) NULL COMMENT '해결 담당자',
    is_noise BOOLEAN NOT NULL DEFAULT FALSE COMMENT '노이즈 여부',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '레코드 생성 시각',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '레코드 수정 시각',
    INDEX idx_incident_key (incident_key),
    INDEX idx_status (status),
    INDEX idx_last_seen_at (last_seen_at),
    INDEX idx_cluster_namespace_service (cluster, namespace, service),
    INDEX idx_service_category (service_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='사건 관리 테이블';

-- incident_alert_links 테이블 제거 (단순화)
-- grafana_alerts.incident_id FK로 직접 연결 관리

-- silences 테이블 제거 (이번 단순화 범위에서 제외)

