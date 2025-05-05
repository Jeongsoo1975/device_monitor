# src/cli.py - CLI 인터페이스 처리 모듈
import argparse
import logging
import sys
import os
from .utils import setup_logging, load_config
from .monitor import run_monitor
from .db_manager import init_database, store_events, get_recent_events

logger = logging.getLogger("DeviceMonitor.CLI")

def parse_args():
    """명령줄 인수를 파싱합니다."""
    parser = argparse.ArgumentParser(
        description="장치 모니터링 및 이벤트 로그 분석 도구",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 서브 명령어 파서 추가
    subparsers = parser.add_subparsers(dest='command', help='수행할 명령')
    
    # 1. 모니터 실행 명령
    monitor_parser = subparsers.add_parser('monitor', help='장치 및 이벤트 로그 모니터링 실행')
    monitor_parser.add_argument(
        '--config', '-c',
        default='config/config.yaml',
        help='설정 파일 경로'
    )
    monitor_parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='로그 출력 최소화 (오류만 표시)'
    )
    monitor_parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='상세 로그 출력 (디버그 정보 포함)'
    )
    monitor_parser.add_argument(
        '--no-llm', 
        action='store_true',
        help='LLM 분석 기능 비활성화'
    )
    
    # 2. 과거 로그 조회 명령
    history_parser = subparsers.add_parser('history', help='저장된 이벤트 로그 및 분석 결과 조회')
    history_parser.add_argument(
        '--days', '-d',
        type=int, 
        default=7,
        help='조회할 기간(일)'
    )
    history_parser.add_argument(
        '--limit', '-l',
        type=int,
        default=100,
        help='최대 표시 이벤트 수'
    )
    history_parser.add_argument(
        '--output', '-o',
        default=None,
        help='결과 출력 파일 경로 (기본: 콘솔 출력)'
    )
    
    # 3. 데이터베이스 초기화 명령
    db_parser = subparsers.add_parser('initdb', help='데이터베이스 초기화/생성')
    db_parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='기존 데이터베이스가 있을 경우 덮어쓰기'
    )
    
    # 인수가 없을 경우 기본값 설정
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    return parser.parse_args()

def run_cli():
    """명령줄 인터페이스의 메인 함수입니다."""
    args = parse_args()
    
    # 설정 파일 로드 및 로거 초기화
    config_path = getattr(args, 'config', 'config/config.yaml')
    if not os.path.exists(config_path):
        print(f"오류: 설정 파일 '{config_path}'을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)
    
    config = load_config(config_path)
    if config is None:
        print("오류: 설정 파일 로드에 실패했습니다.", file=sys.stderr)
        sys.exit(1)
    
    # 로그 레벨 조정 (CLI 인수에 기반)
    if hasattr(args, 'quiet') and args.quiet:
        config['logging']['log_level_console'] = 'ERROR'
    elif hasattr(args, 'verbose') and args.verbose:
        config['logging']['log_level_console'] = 'DEBUG'
    
    # 로거 설정 - 두 번째 매개변수를 전달하도록 수정
    logger = setup_logging(config_path=config_path, config=config)
    logger.debug(f"명령: {args.command}, 인수: {args}")
    
    # 명령에 기반한 작업 수행
    if args.command == 'monitor':
        logger.info("모니터링 모드로 실행합니다.")
        # LLM 비활성화 옵션 처리
        if args.no_llm:
            logger.info("LLM 분석 기능을 비활성화합니다.")
            if 'llm' in config:
                config['llm']['enabled'] = False
        run_monitor(config)
    
    elif args.command == 'history':
        logger.info(f"최근 {args.days}일간의 이벤트 내역을 조회합니다. (최대 {args.limit}개)")
        events = get_recent_events(days=args.days, limit=args.limit)
        
        # 결과 출력 (파일 또는 콘솔)
        if args.output:
            try:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write("=== 이벤트 내역 조회 결과 ===\n")
                    for event in events:
                        f.write(f"[{event['timestamp']}] {event['source']} (ID: {event['event_id']})\n")
                        f.write(f"메시지: {event['message']}\n")
                        if event['llm_analysis']:
                            f.write(f"LLM 분석: {event['llm_analysis']}\n")
                        f.write("-" * 50 + "\n")
                logger.info(f"결과가 '{args.output}' 파일에 저장되었습니다.")
            except Exception as e:
                logger.error(f"파일 저장 중 오류 발생: {e}")
                sys.exit(1)
        else:
            print("=== 이벤트 내역 조회 결과 ===")
            for event in events:
                print(f"[{event['timestamp']}] {event['source']} (ID: {event['event_id']})")
                print(f"메시지: {event['message']}")
                if event['llm_analysis']:
                    print(f"LLM 분석: {event['llm_analysis']}")
                print("-" * 50)
    
    elif args.command == 'initdb':
        logger.info("데이터베이스 초기화를 시작합니다.")
        success = init_database(force=args.force)
        if success:
            logger.info("데이터베이스 초기화가 완료되었습니다.")
        else:
            logger.error("데이터베이스 초기화 실패!")
            sys.exit(1)
    
    else:
        print("오류: 알 수 없는 명령입니다.")
        sys.exit(1)

if __name__ == "__main__":
    run_cli()
