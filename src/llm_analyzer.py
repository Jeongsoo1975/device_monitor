# src/llm_analyzer.py
import requests
import json
import logging
import re
from typing import List, Dict, Any, Optional
import datetime

# 로거 인스턴스 가져오기 (monitor.py에서 설정된 로거 사용)
logger = logging.getLogger("DeviceMonitor.LLMAnalyzer")

def preprocess_logs(log_details: List[str], max_logs: int = 20) -> str:
    """
    로그 데이터를 전처리하여 LLM에 보내기 좋은 형태로 변환합니다.
    - 중복 제거
    - 시간순 정렬
    - 이벤트 별 그룹화
    """
    if not log_details:
        return "분석할 관련 이벤트 로그 내용이 없습니다."
    
    # 최근 로그만 사용
    recent_logs = log_details[:max_logs]
    
    # 시간 정보 추출 및 정렬
    parsed_logs = []
    for log in recent_logs:
        try:
            # 시간 추출 (시간: 2023-05-01 12:34:56 형식 가정)
            time_match = re.search(r'시간: ([\d-]+ [\d:]+)', log)
            if time_match:
                time_str = time_match.group(1)
                # 이벤트 ID 추출
                event_id_match = re.search(r'ID: (\d+)', log)
                event_id = event_id_match.group(1) if event_id_match else "알 수 없음"
                # 소스 추출
                source_match = re.search(r'소스: ([^,]+)', log)
                source = source_match.group(1).strip() if source_match else "알 수 없음"
                
                parsed_logs.append({
                    'time': time_str,
                    'timestamp': datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S'),
                    'source': source,
                    'event_id': event_id,
                    'full_log': log
                })
        except Exception as e:
            logger.debug(f"로그 파싱 실패 (무시됨): {e}")
            parsed_logs.append({
                'time': '1970-01-01 00:00:00',
                'timestamp': datetime.datetime.min,
                'source': "파싱 실패",
                'event_id': "0",
                'full_log': log
            })
    
    # 시간순 정렬
    sorted_logs = sorted(parsed_logs, key=lambda x: x['timestamp'])
    
    # 그룹화 (소스+이벤트ID 기준)
    grouped_logs = {}
    for log in sorted_logs:
        key = f"{log['source']} (ID: {log['event_id']})"
        if key not in grouped_logs:
            grouped_logs[key] = []
        grouped_logs[key].append(log)
    
    # 최종 포맷팅
    result = []
    result.append(f"## 요약 정보")
    result.append(f"- 총 로그 수: {len(sorted_logs)}개")
    result.append(f"- 시간 범위: {sorted_logs[0]['time']} ~ {sorted_logs[-1]['time']}")
    result.append(f"- 이벤트 소스 유형: {len(grouped_logs)}개\n")
    
    for group_key, logs in grouped_logs.items():
        result.append(f"## {group_key} - {len(logs)}건")
        # 각 그룹에서 처음 3개와 마지막 2개 로그만 표시 (너무 많을 경우)
        display_logs = logs
        if len(logs) > 5:
            display_logs = logs[:3] + logs[-2:]
            result.append(f"전체 {len(logs)}건 중 처음 3건과 마지막 2건만 표시합니다.")
        
        for i, log in enumerate(display_logs):
            # 시간 정보 추출하여 앞에 표시
            result.append(f"[{log['time']}] {log['full_log']}")
        
        result.append("")  # 빈 줄 추가
    
    return "\n".join(result)

def analyze_logs_with_llm(log_details, config, api_key):
    """로그 상세 정보를 받아 LLM API를 호출하고 분석 결과를 반환합니다."""
    if not api_key:
        logger.error("LLM 분석을 위한 API 키가 제공되지 않았습니다.")
        return "API 키 없음"

    llm_config = config.get('llm', {})
    api_url = llm_config.get('api_url')
    model = llm_config.get('model')
    timeout = llm_config.get('request_timeout', 60)
    temperature = llm_config.get('temperature', 0.5)
    max_logs = llm_config.get('max_log_details_for_llm', 20)
    abnormal_keywords = llm_config.get('abnormal_keywords', [])

    if not api_url or not model:
        logger.error("LLM 설정(api_url, model)이 설정 파일에 없습니다.")
        return "LLM 설정 오류"

    # LLM에 전달할 로그 데이터 전처리
    log_summary = preprocess_logs(log_details, max_logs)
    if not log_summary or log_summary == "분석할 관련 이벤트 로그 내용이 없습니다.":
        return "분석할 로그 내용 없음"

    # 검색 기준 정보 추가
    event_config = config.get('event_log', {})
    sources = event_config.get('target_sources', [])
    ids = event_config.get('target_event_ids', [])
    criteria_info = f"분석 기준 - 소스: {sources}, ID: {ids}"

    # 개선된 프롬프트 작성
    prompt = f"""# 이벤트 로그 분석 요청

## 작업 개요
당신은 Windows 이벤트 로그 분석 전문가로, 시스템에서 발생한 장치 연결 끊김 또는 하드웨어 관련 문제에 대한 패턴을 찾는 작업을 수행합니다.

## 분석 대상
- 이벤트 로그: Windows '{event_config.get('log_name', 'System')}' 이벤트 로그
- {criteria_info}
- 수집 시점: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 분석해야 할 사항
1. 이벤트 중 비정상적인 패턴이 있는지 확인 (특히 장치 연결 끊김 현상)
2. 반복적으로 발생하는 오류가 있는지
3. 문제가 특정 시간대에 집중되는지
4. 연관된 하드웨어 문제의 명확한 원인이 있는지

## 응답 형식
다음 형식으로 분석 결과를 작성해주세요:
1. 요약 (한 문장으로 정상/비정상 여부)
2. 패턴 분석 (발견된 패턴 설명)
3. 문제 원인 (가장 가능성 높은 원인)
4. 권장사항 (문제 해결을 위한 제안)

## 판단 기준
- 같은 이벤트가 짧은 시간 내에 반복적으로 발생하면 비정상으로 간주
- 여러 관련 이벤트가 특정 시점을 기준으로 연쇄적으로 발생하면 비정상으로 간주
- 장치가 예기치 않게 제거되거나 연결 끊김이 보고되면 비정상으로 간주
- 모든 판단에는 명확한 근거 제시 필요

## 로그 데이터
아래는 전처리된 로그 정보입니다. 이를 기반으로 분석해주세요:

{log_summary}
"""

    # 개선된 시스템 메시지
    system_message = """당신은 Windows 시스템 이벤트 로그 분석 전문가입니다. 하드웨어 장치 연결 문제, 드라이버 오류, 시스템 장애 패턴을 식별하는 데 특화되어 있습니다.
분석 시에는 다음 원칙을 따르세요:
1. 데이터에 기반한 객관적 분석 제공
2. 명확한 패턴이 있을 때만 비정상으로 판단
3. 불확실한 경우 '추가 모니터링 필요' 권고
4. 기술적 용어와 일반 사용자 용어를 적절히 혼합하여 설명
5. 복잡한 기술적 문제도 명확하게 설명"""

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "messages": [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "model": model,
        "stream": False,
        "temperature": temperature
    }

    logger.info(f"'{model}' 모델로 LLM 분석 요청 시작...")
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=timeout)
        response.raise_for_status()  # HTTP 오류 시 예외 발생 (4xx, 5xx)

        result = response.json()
        if result.get("choices") and len(result["choices"]) > 0:
            message = result["choices"][0].get("message")
            if message and message.get("content"):
                llm_response_content = message["content"]
                logger.info("LLM 분석 응답 수신 성공.")
                logger.debug(f"LLM 응답 내용: {llm_response_content[:200]}...")  # 응답 일부만 디버그 로깅

                # 응답 내용 기반으로 비정상 패턴 키워드 검사
                is_abnormal = any(keyword in llm_response_content.lower() for keyword in abnormal_keywords)
                if is_abnormal:
                    logger.warning("LLM 분석 결과: 비정상 패턴 의심.")
                    return f"비정상 패턴 의심됨: {llm_response_content}"
                else:
                    logger.info("LLM 분석 결과: 명확한 비정상 패턴 언급 없음.")
                    return f"정상 범위 추정: {llm_response_content}"
            else:
                logger.error(f"LLM 응답 형식 오류: content 누락. 응답: {result}")
                return "LLM 응답 형식 오류"
        else:
            logger.error(f"LLM 응답 형식 오류: choices 누락. 응답: {result}")
            return "LLM 응답 형식 오류"

    except requests.exceptions.Timeout:
        logger.error(f"LLM API 호출 시간 초과 ({timeout}초).")
        return "LLM API 시간 초과"
    except requests.exceptions.ConnectionError as e:
        logger.error(f"LLM API 연결 오류: {e}", exc_info=True)
        return "LLM API 연결 오류"
    except requests.exceptions.RequestException as e:
        logger.error(f"LLM API 요청 중 오류 발생: {e}", exc_info=True)
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"LLM API 응답 코드: {e.response.status_code}, 내용: {e.response.text[:500]}")
        return f"LLM API 요청 오류: {e.__class__.__name__}"
    except json.JSONDecodeError as e:
        logger.error(f"LLM API 응답 JSON 파싱 오류: {e}", exc_info=True)
        logger.error(f"오류 발생 시 응답 내용: {response.text[:500]}")
        return "LLM 응답 파싱 오류"
    except Exception as e:
        logger.error(f"LLM 분석 중 예기치 않은 오류 발생: {e}", exc_info=True)
        return "LLM 분석 중 알 수 없는 오류"
