# src/monitor.py
import platform
import logging
import sys
import os
import time
import datetime
import re
from typing import List, Dict, Tuple, Any, Optional

# 필요한 모듈 임포트
from .utils import setup_logging, load_config, load_api_key
from .llm_analyzer import analyze_logs_with_llm
from .db_manager import init_database, start_scan_session, end_scan_session, store_hardware_info, store_events

# Windows 전용 라이브러리 임포트 (오류 처리 포함)
is_windows = platform.system() == "Windows"
wmi = None
serial = None
win32evtlog = None
win32evtlogutil = None
win32con = None

try:
    import serial.tools.list_ports
except ImportError:
    print("오류: 'pyserial' 라이브러리가 없습니다. 'pip install pyserial'", file=sys.stderr)
    sys.exit(1)

if is_windows:
    try:
        import wmi
    except ImportError:
        print("오류: 'WMI' 라이브러리가 없습니다. 'pip install WMI && pip install pypiwin32'", file=sys.stderr)
        is_windows = False # WMI 사용 불가 처리
    except Exception as e:
         print(f"WMI 초기화 오류: {e}", file=sys.stderr)
         is_windows = False

    try:
        import win32evtlog
        import win32evtlogutil
        import win32con
    except ImportError:
         print("오류: 'pywin32' 라이브러리가 없습니다. 'pip install pypiwin32'", file=sys.stderr)
         is_windows = False

# --- 하드웨어 정보 함수 ---
def get_com_ports(logger, session_id=None):
    """사용 가능한 COM 포트 목록을 수집하고 로깅합니다."""
    logger.info("COM 포트 정보 수집 시작...")
    try:
        ports = serial.tools.list_ports.comports()
        if not ports:
            logger.info("사용 가능한 COM 포트를 찾을 수 없습니다.")
            return []
        
        logger.info(f"발견된 COM 포트 수: {len(ports)}")
        com_devices = []
        
        for port in ports:
            logger.info(f"  장치: {port.device}, 설명: {port.description}, HWID: {port.hwid}")
            com_devices.append({
                'name': port.device,
                'description': port.description,
                'device_id': port.hwid
            })
        
        # 데이터베이스에 저장 (session_id가 있는 경우)
        if session_id and com_devices:
            count = store_hardware_info(session_id, 'COM', com_devices)
            logger.debug(f"{count}개의 COM 포트 정보가 데이터베이스에 저장되었습니다.")
            
        return com_devices
    except Exception as e:
        logger.error(f"COM 포트 검색 중 오류 발생: {e}", exc_info=True)
        return []

def get_cameras_windows(logger, session_id=None):
    """WMI를 사용하여 연결된 카메라 목록을 수집하고 로깅합니다."""
    if not is_windows or wmi is None:
        logger.warning("Windows 환경이 아니거나 WMI 모듈 로드 실패로 카메라 정보를 가져올 수 없습니다.")
        return []
    
    logger.info("카메라 정보 수집 시작 (WMI 사용)...")
    try:
        wmi_conn = wmi.WMI()
        query = "SELECT Name, Description, DeviceID FROM Win32_PnPEntity WHERE ClassGuid='{6bdd1fc6-810f-11d0-bec7-08002be2092f}' OR ClassGuid='{ca3e7ab9-b4c3-4ae6-8251-579ef933890f}' OR PNPClass='Camera' OR Service='usbvideo'"
        cameras = wmi_conn.query(query)
        
        if not cameras:
            logger.info("연결된 카메라를 찾을 수 없습니다 (WMI).")
            return []
        
        logger.info(f"발견된 카메라 수 (중복 포함 가능): {len(cameras)}")
        unique_cameras = {cam.DeviceID: cam for cam in cameras}
        camera_devices = []
        
        for _, cam in unique_cameras.items():
            logger.info(f"  카메라: {cam.Name}, 설명: {cam.Description if hasattr(cam, 'Description') else '없음'}, ID: {cam.DeviceID}")
            camera_devices.append({
                'name': cam.Name,
                'description': getattr(cam, 'Description', ''),
                'device_id': cam.DeviceID
            })
        
        # 데이터베이스에 저장 (session_id가 있는 경우)
        if session_id and camera_devices:
            count = store_hardware_info(session_id, 'Camera', camera_devices)
            logger.debug(f"{count}개의 카메라 정보가 데이터베이스에 저장되었습니다.")
            
        return camera_devices
    except wmi.x_wmi as e:
         logger.error(f"WMI 쿼리 오류 (카메라): {e}. 관리자 권한이 필요할 수 있습니다.", exc_info=True)
         return []
    except Exception as e:
        logger.error(f"카메라 정보 수집 중 예기치 않은 오류 발생: {e}", exc_info=True)
        return []

def get_usb_devices_windows(logger, session_id=None):
    """WMI를 사용하여 연결된 USB 장치 목록을 수집하고 로깅합니다."""
    if not is_windows or wmi is None:
        logger.warning("Windows 환경이 아니거나 WMI 모듈 로드 실패로 USB 장치 정보를 가져올 수 없습니다.")
        return []
    
    logger.info("USB 장치 정보 수집 시작 (WMI 사용)...")
    try:
        wmi_conn = wmi.WMI()
        query = "SELECT Name, Description, DeviceID FROM Win32_PnPEntity WHERE DeviceID LIKE 'USB\\%'"
        usb_devices = wmi_conn.query(query)
        
        if not usb_devices:
            logger.info("연결된 USB 장치를 찾을 수 없습니다 (WMI).")
            return []
        
        logger.info(f"발견된 USB 장치 수 (허브, 루트 등 포함): {len(usb_devices)}")
        filtered_devices = [
            dev for dev in usb_devices
            if dev.Name and not any(keyword in dev.Name.lower() for keyword in ['hub', '복합', 'composite', 'root'])
        ]
        
        usb_device_list = []
        if filtered_devices:
            logger.info(f"필터링된 USB 장치 수: {len(filtered_devices)}")
            for dev in filtered_devices:
                logger.info(f"  USB 장치: {dev.Name}, 설명: {getattr(dev, 'Description', '없음')}, ID: {dev.DeviceID}")
                usb_device_list.append({
                    'name': dev.Name,
                    'description': getattr(dev, 'Description', ''),
                    'device_id': dev.DeviceID
                })
        else:
            logger.info("필터링 조건에 맞는 사용자 인식 가능 USB 장치를 찾지 못했습니다.")
        
        # 데이터베이스에 저장 (session_id가 있는 경우)
        if session_id and usb_device_list:
            count = store_hardware_info(session_id, 'USB', usb_device_list)
            logger.debug(f"{count}개의 USB 장치 정보가 데이터베이스에 저장되었습니다.")
            
        return usb_device_list
    except wmi.x_wmi as e:
        logger.error(f"WMI 쿼리 오류 (USB): {e}. 관리자 권한이 필요할 수 있습니다.", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"USB 장치 정보 수집 중 예기치 않은 오류 발생: {e}", exc_info=True)
        return []

# --- 이벤트 로그 분석 함수 ---
def analyze_event_logs(config, logger):
    """이벤트 로그를 분석하여 조건과 일치하는 이벤트 수와 상세 정보를 반환합니다."""
    if not is_windows or win32evtlog is None:
        logger.warning("Windows 환경이 아니거나 pywin32 모듈 로드 실패로 이벤트 로그를 분석할 수 없습니다.")
        return 0, [], []

    evt_conf = config.get('event_log', {})
    log_name = evt_conf.get('log_name', 'System')
    max_events = evt_conf.get('max_events_to_read', 1000)
    target_sources = evt_conf.get('target_sources', [])
    target_event_ids = evt_conf.get('target_event_ids', [])

    logger.info(f"'{log_name}' 이벤트 로그 분석 시작 (최대 {max_events}개)...")
    logger.info(f"  검색 조건 - 소스: {target_sources}, ID: {target_event_ids}")

    if not target_sources and not target_event_ids:
        logger.error("분석할 이벤트 소스 또는 ID가 설정 파일에 지정되지 않았습니다.")
        return 0, [], []

    matched_events = []  # 데이터베이스에 저장할 구조화된 이벤트 정보
    matched_event_details = []  # 로그 문자열 (LLM 분석용)
    event_count = 0
    handle = None
    total_read = 0

    try:
        handle = win32evtlog.OpenEventLog(None, log_name)
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

        while total_read < max_events:
            try:
                # 버퍼 크기를 조절하여 메모리 사용량 관리 가능
                events = win32evtlog.ReadEventLog(handle, flags, 0, 8192)
            except win32evtlog.error as e:
                 # ERROR_NO_MORE_ITEMS (18) 는 정상적인 종료 조건일 수 있음
                 if e.winerror == 18:
                     logger.debug("더 이상 읽을 이벤트가 없습니다.")
                     break
                 else:
                     raise # 다른 win32 오류는 다시 발생시킴
            if not events:
                logger.debug("이벤트 읽기 결과가 비어있습니다.")
                break # 더 이상 이벤트 없음

            batch_size = len(events)
            events_to_process_in_batch = min(batch_size, max_events - total_read)

            for i in range(events_to_process_in_batch):
                event = events[i]
                event_id = event.EventID & 0xFFFF
                source_name = event.SourceName

                match_found = False
                if target_sources and source_name in target_sources:
                    match_found = True
                if not match_found and target_event_ids and event_id in target_event_ids:
                    match_found = True

                if match_found:
                    event_count += 1
                    try:
                        msg = win32evtlogutil.SafeFormatMessage(event, log_name)
                        event_time = event.TimeGenerated.Format('%Y-%m-%d %H:%M:%S')
                        event_iso_time = event.TimeGenerated.Format('%Y-%m-%dT%H:%M:%S')
                        
                        # 로그 문자열 생성 (LLM용)
                        detail = f"시간: {event_time}, 소스: {source_name}, ID: {event_id}, 메시지: {msg.strip()}"
                        matched_event_details.append(detail)
                        
                        # 구조화된 이벤트 정보 생성 (DB 저장용)
                        matched_events.append({
                            'timestamp': event_iso_time,
                            'source': source_name,
                            'event_id': event_id,
                            'message': msg.strip(),
                            'llm_analysis': '',  # 나중에 업데이트
                            'abnormal': False    # 나중에 업데이트
                        })
                        
                        logger.debug(f"  조건 일치 이벤트 발견: {detail[:150]}...") 
                    except Exception as format_err:
                        event_time = event.TimeGenerated.Format('%Y-%m-%d %H:%M:%S')
                        event_iso_time = event.TimeGenerated.Format('%Y-%m-%dT%H:%M:%S')
                        
                        error_msg = f"포맷 오류: {format_err}"
                        detail = f"시간: {event_time}, 소스: {source_name}, ID: {event_id}, 메시지: ({error_msg})"
                        matched_event_details.append(detail)
                        
                        matched_events.append({
                            'timestamp': event_iso_time,
                            'source': source_name,
                            'event_id': event_id,
                            'message': error_msg,
                            'llm_analysis': '',
                            'abnormal': False
                        })
                        
                        logger.warning(f"이벤트 메시지 포맷팅 오류 발생: {format_err}", exc_info=False)

            total_read += events_to_process_in_batch
            if total_read >= max_events:
                logger.info(f"최대 검색 이벤트 수 ({max_events}개) 도달.")
                break

        logger.info(f"총 분석된 최근 이벤트 수: {total_read}")
        logger.info(f"지정된 기준과 일치하는 이벤트 수: {event_count}")
        return event_count, matched_event_details, matched_events

    except win32evtlog.error as e:
        logger.error(f"'{log_name}' 이벤트 로그 접근 오류: {e}. 권한 또는 로그 이름 확인 필요.", exc_info=True)
        return 0, [], []
    except Exception as e:
        logger.error(f"이벤트 로그 분석 중 예기치 않은 오류 발생: {e}", exc_info=True)
        return 0, [], []
    finally:
        if handle:
            try:
                win32evtlog.CloseEventLog(handle)
            except Exception as close_err:
                 logger.error(f"이벤트 로그 핸들 닫기 오류: {close_err}", exc_info=True)

def parse_event_log_string(log_string):
    """이벤트 로그 문자열을 파싱하여 구조화된 데이터로 변환합니다."""
    # 로그 문자열 예시: "시간: 2023-05-01 12:34:56, 소스: Microsoft-Windows-Kernel-PnP, ID: 2102, 메시지: ..."
    
    try:
        # 정규식을 사용한 파싱
        time_match = re.search(r'시간: ([\d-]+ [\d:]+)', log_string)
        source_match = re.search(r'소스: ([^,]+)', log_string)
        id_match = re.search(r'ID: (\d+)', log_string)
        message_match = re.search(r'메시지: (.+)$', log_string)
        
        if time_match and source_match and id_match:
            event_time = time_match.group(1)
            source = source_match.group(1).strip()
            event_id = int(id_match.group(1))
            message = message_match.group(1).strip() if message_match else ""
            
            # ISO 형식으로 시간 변환
            try:
                dt = datetime.datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S')
                iso_time = dt.isoformat()
            except ValueError:
                iso_time = datetime.datetime.now().isoformat()
            
            return {
                'timestamp': iso_time,
                'source': source,
                'event_id': event_id,
                'message': message,
                'llm_analysis': '',
                'abnormal': False
            }
    except Exception:
        pass
    
    return None  # 파싱 실패

# --- 메인 실행 함수 ---
def run_monitor(config=None):
    """메인 모니터링 작업을 수행합니다."""
    if config is None:
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
        config = load_config(config_path)
        if config is None:
            print("치명적 오류: 설정 파일을 로드할 수 없습니다. 프로그램을 종료합니다.", file=sys.stderr)
            sys.exit(1)

    # 로거 설정
    logger = logging.getLogger("DeviceMonitor")
    if not logger.handlers:
        logger = setup_logging(config_path=None, config=config)
    
    logger.info("="*40)
    logger.info(" 장치 및 이벤트 로그 모니터 스크립트 시작")
    logger.info("="*40)

    # 데이터베이스 초기화 확인
    init_database(force=False)
    
    # 스캔 세션 시작
    session_id = start_scan_session()
    if session_id is None:
        logger.warning("스캔 세션을 생성할 수 없어 DB 저장 기능이 제한됩니다.")
    else:
        logger.info(f"스캔 세션 시작 (ID: {session_id})")

    # API 키 로드
    api_key = load_api_key(logger)
    if api_key is None and config.get('llm', {}).get('enabled', True):
        logger.warning("API 키를 로드할 수 없어 LLM 분석 기능이 비활성화됩니다.")
        config['llm']['enabled'] = False

    # --- 1. 하드웨어 정보 수집 ---
    logger.info("[단계 1/3] 하드웨어 정보 수집")
    hw_devices_found = 0
    
    # COM 포트 정보 수집
    com_devices = get_com_ports(logger, session_id)
    hw_devices_found += len(com_devices)
    
    # Windows 전용 장치 정보 수집
    if is_windows:
        camera_devices = get_cameras_windows(logger, session_id)
        hw_devices_found += len(camera_devices)
        
        usb_devices = get_usb_devices_windows(logger, session_id)
        hw_devices_found += len(usb_devices)
    else:
        logger.info("Windows 환경이 아니므로 카메라 및 USB 정보 수집(WMI)을 건너뜁니다.")

    # --- 2. 이벤트 로그 분석 ---
    logger.info("[단계 2/3] 이벤트 로그 분석")
    event_count, event_log_strings, event_objects = analyze_event_logs(config, logger)
    
    # --- 3. LLM 분석 (조건 충족 시) ---
    logger.info("[단계 3/3] LLM 분석 (조건 충족 시)")
    llm_config = config.get('llm', {})
    llm_check_threshold = llm_config.get('check_threshold', 5)
    llm_enabled = llm_config.get('enabled', True)
    llm_analysis_performed = False
    llm_result = "LLM 분석 미수행"
    session_summary = f"이벤트 발견: {event_count}개, 장치 발견: {hw_devices_found}개"

    if event_count >= llm_check_threshold and llm_enabled:
        logger.warning(f"지정된 이벤트가 임계값({llm_check_threshold}회) 이상 ({event_count}회) 발생하여 LLM 분석을 시작합니다.")
        if api_key:
            # LLM 분석 수행
            llm_result = analyze_logs_with_llm(event_log_strings, config, api_key)
            llm_analysis_performed = True
            logger.info(f"LLM 분석 결과: {llm_result}") 
            
            # 비정상 패턴 여부 확인
            is_abnormal = False
            if "비정상 패턴 의심됨" in llm_result:
                logger.critical("!!! LLM 경고: 비정상적인 연결 끊김 패턴이 의심됩니다. 상세 점검 필요 !!!")
                is_abnormal = True
                session_summary += ", 비정상 패턴 감지됨"
            
            # 이벤트 객체에 LLM 분석 결과 추가
            for event in event_objects:
                event['llm_analysis'] = llm_result
                event['abnormal'] = is_abnormal
            
            # 이벤트 저장 (DB)
            if session_id and event_objects:
                stored_count = store_events(session_id, event_objects)
                logger.debug(f"{stored_count}개의 이벤트가 데이터베이스에 저장되었습니다.")
        else:
            logger.error("LLM 분석 필요 조건이 충족되었으나 API 키가 없어 분석을 건너뜁니다.")
            session_summary += ", LLM 분석 실패 (API 키 없음)"
    else:
        if not llm_enabled:
            logger.info("LLM 분석 기능이 비활성화되어 있습니다.")
            session_summary += ", LLM 분석 비활성화됨"
        else:
            logger.info(f"이벤트 발생 횟수({event_count}회)가 LLM 검사 임계값({llm_check_threshold}회) 미만입니다.")
            session_summary += ", LLM 분석 임계값 미달"
        
        # 이벤트 저장 (DB) - LLM 분석 없이
        if session_id and event_objects:
            stored_count = store_events(session_id, event_objects)
            logger.debug(f"{stored_count}개의 이벤트가 데이터베이스에 저장되었습니다.")

    # 스캔 세션 종료
    if session_id:
        end_scan_session(
            session_id, 
            events_found=event_count,
            hw_devices_found=hw_devices_found,
            llm_analysis_performed=1 if llm_analysis_performed else 0,
            summary=session_summary
        )
        logger.info(f"스캔 세션 종료 (ID: {session_id})")

    logger.info("="*40)
    logger.info(" 스크립트 실행 완료.")
    logger.info("="*40)
    
    return {
        'event_count': event_count,
        'hw_devices_found': hw_devices_found,
        'llm_analysis_performed': llm_analysis_performed,
        'llm_result': llm_result,
        'session_id': session_id
    }

if __name__ == "__main__":
    # 스크립트가 직접 실행될 때 run_monitor() 함수를 호출합니다.
    run_monitor()
