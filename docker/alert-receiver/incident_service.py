"""
Incident 비즈니스 로직 (Ack, Resolve, Mute)
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import pymysql


def acknowledge_incident(conn, incident_id: str, user: str) -> bool:
    """
    Incident를 Acknowledged 상태로 변경
    
    Returns: 성공 여부
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE incidents 
                SET status = 'acknowledged',
                    acknowledged_time = %s,
                    updated_at = %s
                WHERE incident_id = %s
            """, (
                datetime.now(),
                datetime.now(),
                incident_id
            ))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"❌ Incident ACK 실패: {e}")
        return False


def resolve_incident(conn, incident_id: str, user: str) -> bool:
    """
    Incident를 Resolved 상태로 변경
    
    Returns: 성공 여부
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE incidents 
                SET status = 'resolved',
                    resolved_time = %s,
                    resolved_by = %s,
                    updated_at = %s
                WHERE incident_id = %s
            """, (
                datetime.now(),
                user,
                datetime.now(),
                incident_id
            ))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"❌ Incident Resolve 실패: {e}")
        return False


def mute_incident(conn, incident_key: str, duration_minutes: int, user: str) -> bool:
    """
    Incident 알림 음소거
    
    Args:
        conn: DB 연결
        incident_key: 사건 유형 키
        duration_minutes: 음소거 시간 (분)
        user: 사용자
    
    Returns: 성공 여부
    """
    try:
        with conn.cursor() as cursor:
            starts_at = datetime.now()
            ends_at = starts_at + timedelta(minutes=duration_minutes)
            
            cursor.execute("""
                INSERT INTO silences 
                (incident_key, starts_at, ends_at, created_by, reason)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                incident_key,
                starts_at,
                ends_at,
                user,
                f"Muted for {duration_minutes} minutes"
            ))
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        print(f"❌ Incident Mute 실패: {e}")
        return False


def check_silence(conn, incident_key: str) -> bool:
    """
    현재 시간에 해당 incident_key가 음소거 상태인지 확인
    
    Returns: True if muted, False otherwise
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 1 FROM silences 
                WHERE incident_key = %s 
                  AND NOW() BETWEEN starts_at AND ends_at
                LIMIT 1
            """, (incident_key,))
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        print(f"❌ Silence 체크 실패: {e}")
        return False


def get_incident_info(conn, incident_id: str) -> Optional[Dict[str, Any]]:
    """
    Incident 정보 조회
    
    Returns: Incident 정보 dict 또는 None
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT incident_id, incident_key, status, severity, cluster, namespace, 
                       phase, service, alert_count, start_time, first_seen_at
                FROM incidents 
                WHERE incident_id = %s
            """, (incident_id,))
            return cursor.fetchone()
    except Exception as e:
        print(f"❌ Incident 정보 조회 실패: {e}")
        return None

