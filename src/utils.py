# src/utils.py
import logging
import logging.handlers
import os
import sys
import yaml
from dotenv import load_dotenv

def setup_logging(config_path="config/config.yaml", config=None):
    """설정 파일 기반으로 로깅 시스템을 설정하고 로거를 반환합니다."""
    log_conf = {}
    
    # config 매개변수가 제공된 경우 사용, 아니면 파일에서 로드
    if config is not None:
        log_conf = config.get('logging', {})
    else:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                log_conf = config_data.get('logging', {})
        except FileNotFoundError:
            print(f"오류: 설정 파일 '{config_path}'를 찾을 수 없습니다.", file=sys.stderr)
        except yaml.YAMLError as e:
            print(f"오류: 설정 파일 파싱 중 오류 발생: {e}", file=sys.stderr)

    log_file = log_conf.get('log_file', 'logs/app.log')
    log_level_console_str = log_conf.get('log_level_console', 'INFO').upper()
    log_level_file_str = log_conf.get('log_level_file', 'DEBUG').upper()
    log_format = log_conf.get('log_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    log_level_console = getattr(logging, log_level_console_str, logging.INFO)
    log_level_file = getattr(logging, log_level_file_str, logging.DEBUG)

    logger = logging.getLogger("DeviceMonitor") # 애플리케이션 로거 이름 지정
    logger.setLevel(logging.DEBUG) # 핸들러에서 레벨 제어하도록 함

    # 이전 핸들러 제거
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(log_format)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level_console)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (로그 디렉토리 생성 포함)
    try:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        # RotatingFileHandler 사용 예시 (로그 파일 크기 기반 로테이션)
        # file_handler = logging.handlers.RotatingFileHandler(
        #     log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        # )
        file_handler = logging.FileHandler(log_file, encoding='utf-8') # 기본 파일 핸들러
        file_handler.setLevel(log_level_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"로그 파일 핸들러 설정 중 오류 발생: {e}", file=sys.stderr)

    return logger

def load_config(config_path="config/config.yaml", logger=None):
    """YAML 설정 파일을 로드합니다."""
    if logger is None: # 로거가 없으면 기본 로거 사용 (주로 초기 단계)
        logger = logging.getLogger("ConfigLoader")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            logger.info(f"설정 파일 '{config_path}' 로드 성공.")
            return config
    except FileNotFoundError:
        logger.error(f"설정 파일 '{config_path}'를 찾을 수 없습니다.")
        return None
    except yaml.YAMLError as e:
        logger.error(f"설정 파일 파싱 중 오류 발생: {e}", exc_info=True)
        return None
    except Exception as e:
         logger.error(f"설정 파일 로드 중 예기치 않은 오류 발생: {e}", exc_info=True)
         return None

def load_api_key(logger=None):
    """ .env 파일에서 API 키를 로드합니다. """
    if logger is None:
        logger = logging.getLogger("ApiKeyLoader")

    try:
        load_dotenv()
        api_key = os.getenv("GROK_API_KEY")
        if not api_key:
            logger.error("GROK_API_KEY 환경 변수를 찾을 수 없습니다. .env 파일을 확인하세요.")
            return None
        logger.debug("GROK API 키 로드 성공 (값은 로깅되지 않음).")
        return api_key
    except Exception as e:
        logger.error(f".env 파일 로드 또는 API 키 검색 중 오류 발생: {e}", exc_info=True)
        return None