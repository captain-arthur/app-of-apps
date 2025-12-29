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
                    acknowledged_by = %s,
                    updated_at = %s
                WHERE incident_id = %s
            """, (
                datetime.now(),
                user,
                datetime.now(),
                incident_id
            ))
            # commit 제거: 호출자에서 처리
            return cursor.rowcount > 0
    except Exception as e:
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
            # commit 제거: 호출자에서 처리
            return cursor.rowcount > 0
    except Exception as e:
        print(f"❌ Incident Resolve 실패: {e}")
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

