# src/db_manager.py - 데이터베이스 관리 모듈
import os
import sqlite3
import logging
import datetime
import json
from pathlib import Path

logger = logging.getLogger("DeviceMonitor.DBManager")

def get_db_path():
    """데이터베이스 파일 경로를 반환합니다."""
    # 현재 스크립트 경로 기준으로 상위 디렉토리(프로젝트 루트)의 data 폴더 생성
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / 'data'
    
    # data 디렉토리가 없으면 생성
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"데이터 디렉토리 생성됨: {data_dir}")
        except Exception as e:
            logger.error(f"데이터 디렉토리 생성 중 오류: {e}")
            return None
    
    db_path = data_dir / 'device_monitor.db'
    return str(db_path)

def init_database(force=False):
    """데이터베이스 및 필요한 테이블을 초기화합니다."""
    db_path = get_db_path()
    if db_path is None:
        return False
    
    # 기존 DB 파일이 있고 force 옵션이 False면 그대로 사용
    if os.path.exists(db_path) and not force:
        logger.info(f"기존 데이터베이스가 존재합니다: {db_path}")
        try:
            # DB 연결 테스트
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # 테이블 존재 여부 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
            if not cursor.fetchone():
                logger.warning("기존 데이터베이스에 필요한 테이블이 없습니다. 테이블을 생성합니다.")
                return create_tables(conn)
            conn.close()
            return True
        except sqlite3.Error as e:
            logger.error(f"기존 데이터베이스 연결 오류: {e}")
            if force:
                logger.warning("force 옵션이 활성화되어 있어 데이터베이스를 재생성합니다.")
                try:
                    os.remove(db_path)
                except Exception as rm_error:
                    logger.error(f"기존 데이터베이스 삭제 오류: {rm_error}")
                    return False
            else:
                return False
    
    # DB 파일이 없거나 강제 재생성 옵션이 있으면 새로 생성
    try:
        logger.info(f"새로운 데이터베이스 생성: {db_path}")
        conn = sqlite3.connect(db_path)
        return create_tables(conn)
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 생성 오류: {e}")
        return False

def create_tables(conn):
    """필요한 테이블을 생성합니다."""
    try:
        cursor = conn.cursor()
        
        # 이벤트 로그 저장 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            event_id INTEGER NOT NULL,
            message TEXT,
            llm_analysis TEXT,
            abnormal_flag INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 하드웨어 정보 저장 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS hardware_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            hw_type TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            device_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 스캔 세션 관리 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            events_found INTEGER DEFAULT 0,
            hw_devices_found INTEGER DEFAULT 0,
            llm_analysis_performed INTEGER DEFAULT 0,
            summary TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        logger.debug("데이터베이스 테이블 생성 완료")
        return True
    except sqlite3.Error as e:
        logger.error(f"테이블 생성 오류: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_db_connection():
    """데이터베이스 연결을 반환합니다."""
    db_path = get_db_path()
    if db_path is None:
        return None
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # 컬럼명으로 접근 가능하게 설정
        return conn
    except sqlite3.Error as e:
        logger.error(f"데이터베이스 연결 실패: {e}")
        return None

def start_scan_session():
    """새로운 스캔 세션을 시작하고 세션 ID를 반환합니다."""
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        start_time = datetime.datetime.now().isoformat()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO scan_sessions (start_time) VALUES (?)", (start_time,))
        conn.commit()
        session_id = cursor.lastrowid
        logger.debug(f"새 스캔 세션 시작: ID={session_id}")
        return session_id
    except sqlite3.Error as e:
        logger.error(f"스캔 세션 생성 오류: {e}")
        return None
    finally:
        if conn:
            conn.close()

def end_scan_session(session_id, events_found=0, hw_devices_found=0, llm_analysis_performed=0, summary=None):
    """스캔 세션을 종료하고 결과를 업데이트합니다."""
    if session_id is None:
        return False
    
    conn = get_db_connection()
    if conn is None:
        return False
    
    try:
        end_time = datetime.datetime.now().isoformat()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE scan_sessions SET end_time=?, events_found=?, hw_devices_found=?, "
            "llm_analysis_performed=?, summary=? WHERE id=?",
            (end_time, events_found, hw_devices_found, llm_analysis_performed, summary, session_id)
        )
        conn.commit()
        logger.debug(f"스캔 세션 종료: ID={session_id}, 이벤트={events_found}, 장치={hw_devices_found}")
        return True
    except sqlite3.Error as e:
        logger.error(f"스캔 세션 업데이트 오류: {e}")
        return False
    finally:
        if conn:
            conn.close()

def store_hardware_info(session_id, hw_type, devices):
    """하드웨어 정보를 데이터베이스에 저장합니다."""
    if not devices:
        return 0
    
    conn = get_db_connection()
    if conn is None:
        return 0
    
    try:
        timestamp = datetime.datetime.now().isoformat()
        cursor = conn.cursor()
        count = 0
        
        for device in devices:
            cursor.execute(
                "INSERT INTO hardware_info (timestamp, hw_type, name, description, device_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (timestamp, hw_type, device.get('name', ''), 
                 device.get('description', ''), device.get('device_id', ''))
            )
            count += 1
        
        conn.commit()
        logger.debug(f"{hw_type} 정보 {count}개 저장됨")
        return count
    except sqlite3.Error as e:
        logger.error(f"하드웨어 정보 저장 오류: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def store_events(session_id, events):
    """이벤트 로그 정보를 데이터베이스에 저장합니다."""
    if not events:
        return 0
    
    conn = get_db_connection()
    if conn is None:
        return 0
    
    try:
        cursor = conn.cursor()
        count = 0
        
        for event in events:
            cursor.execute(
                "INSERT INTO events (timestamp, source, event_id, message, llm_analysis, abnormal_flag) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event.get('timestamp', datetime.datetime.now().isoformat()),
                 event.get('source', ''),
                 event.get('event_id', 0),
                 event.get('message', ''),
                 event.get('llm_analysis', ''),
                 1 if event.get('abnormal', False) else 0)
            )
            count += 1
        
        conn.commit()
        logger.debug(f"이벤트 {count}개 저장됨")
        return count
    except sqlite3.Error as e:
        logger.error(f"이벤트 저장 오류: {e}")
        return 0
    finally:
        if conn:
            conn.close()

def get_recent_events(days=7, limit=100):
    """최근 이벤트 로그를 조회합니다."""
    conn = get_db_connection()
    if conn is None:
        return []
    
    try:
        cursor = conn.cursor()
        # 현재 시간 기준으로 days일 전 날짜 계산
        days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        days_ago_str = days_ago.isoformat()
        
        cursor.execute(
            "SELECT * FROM events WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
            (days_ago_str, limit)
        )
        
        rows = cursor.fetchall()
        events = []
        for row in rows:
            event = dict(row)
            # JSON 형식으로 변환 가능하도록 처리
            event['abnormal'] = bool(event['abnormal_flag'])
            del event['abnormal_flag']
            events.append(event)
        
        logger.debug(f"{len(events)}개의 이벤트 조회됨 (최근 {days}일)")
        return events
    except sqlite3.Error as e:
        logger.error(f"이벤트 조회 오류: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_event_statistics(days=30):
    """이벤트 통계 정보를 조회합니다."""
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        cursor = conn.cursor()
        # 현재 시간 기준으로 days일 전 날짜 계산
        days_ago = datetime.datetime.now() - datetime.timedelta(days=days)
        days_ago_str = days_ago.isoformat()
        
        # 일별 이벤트 개수 조회
        cursor.execute("""
            SELECT 
                substr(timestamp, 1, 10) as day, 
                COUNT(*) as count,
                SUM(abnormal_flag) as abnormal_count
            FROM events 
            WHERE timestamp > ? 
            GROUP BY day 
            ORDER BY day
        """, (days_ago_str,))
        
        daily_stats = cursor.fetchall()
        
        # 소스별 이벤트 개수 조회
        cursor.execute("""
            SELECT 
                source, 
                COUNT(*) as count,
                SUM(abnormal_flag) as abnormal_count
            FROM events 
            WHERE timestamp > ? 
            GROUP BY source 
            ORDER BY count DESC
        """, (days_ago_str,))
        
        source_stats = cursor.fetchall()
        
        # 이벤트 ID별 개수 조회
        cursor.execute("""
            SELECT 
                event_id, 
                COUNT(*) as count,
                SUM(abnormal_flag) as abnormal_count
            FROM events 
            WHERE timestamp > ? 
            GROUP BY event_id 
            ORDER BY count DESC
        """, (days_ago_str,))
        
        event_id_stats = cursor.fetchall()
        
        # 결과 조합
        statistics = {
            'period': {
                'start': days_ago_str,
                'end': datetime.datetime.now().isoformat(),
                'days': days
            },
            'daily': [dict(row) for row in daily_stats],
            'by_source': [dict(row) for row in source_stats],
            'by_event_id': [dict(row) for row in event_id_stats],
            'total_events': sum(row['count'] for row in daily_stats),
            'total_abnormal': sum(row['abnormal_count'] for row in daily_stats)
        }
        
        logger.debug(f"이벤트 통계 조회됨 (최근 {days}일)")
        return statistics
    except sqlite3.Error as e:
        logger.error(f"통계 조회 오류: {e}")
        return None
    finally:
        if conn:
            conn.close()

def export_events_to_json(filepath, days=30):
    """이벤트 데이터를 JSON 파일로 내보냅니다."""
    events = get_recent_events(days=days, limit=10000)  # 충분히 큰 수로 설정
    if not events:
        logger.warning("내보낼 이벤트 데이터가 없습니다.")
        return False
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        logger.info(f"{len(events)}개의 이벤트를 '{filepath}'에 저장했습니다.")
        return True
    except Exception as e:
        logger.error(f"JSON 파일 저장 오류: {e}")
        return False
