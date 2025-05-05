#!/usr/bin/env python3
"""
장치 모니터링 및 이벤트 로그 분석 도구

이 스크립트는 시스템에 연결된 하드웨어 정보를 수집하고, Windows 이벤트 로그를
분석하여 장치 연결 끊김과 같은 특정 이벤트의 발생 빈도를 파악합니다.
발견된 이벤트가 임계값을 초과하면 LLM을 활용하여 비정상 패턴을 분석합니다.

사용법:
  python main.py                                # CLI 도움말 표시
  python main.py monitor                        # 모니터링 실행 (기본 설정)
  python main.py monitor --config custom.yaml   # 사용자 정의 설정으로 실행
  python main.py monitor --no-llm               # LLM 분석 비활성화
  python main.py history --days 7               # 최근 7일간의 이벤트 내역 조회
  python main.py initdb                         # 데이터베이스 초기화
"""

import os
import sys
import logging
from src.cli import run_cli
from src.db_manager import init_database
from src.utils import setup_logging, load_config

# 현재 실행 파일의 디렉토리를 Python 경로에 추가 (상대 경로 임포트 지원)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    """메인 함수: CLI 인터페이스 실행"""
    # 필요한 디렉토리 생성
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    # 데이터베이스 초기화 확인
    if not os.path.exists('data/device_monitor.db'):
        print("초기 실행: 데이터베이스를 초기화합니다.")
        init_database()
    
    # CLI 실행
    run_cli()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n프로그램 실행이 사용자에 의해 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"오류 발생: {e}", file=sys.stderr)
        logging.getLogger("DeviceMonitor").error(f"예기치 않은 오류: {e}", exc_info=True)
        sys.exit(1)
