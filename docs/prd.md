# Device Monitor 프로젝트 분석 및 개선 사항

## 프로젝트 개요

Device Monitor는 Windows 시스템에서 연결된 하드웨어(COM 포트, 카메라, USB 장치)를 감지하고, Windows 이벤트 로그를 분석하여 장치 연결 끊김과 같은 특정 이벤트의 발생 빈도를 파악하는 파이썬 애플리케이션입니다. 이벤트 로그 분석 결과를 Grok LLM API에 전송하여 비정상적인 패턴을 식별하는 기능도 포함되어 있습니다.

## 현재 기능

1. **하드웨어 감지**
   - COM 포트 감지 (pyserial 사용)
   - 카메라 감지 (WMI 사용, Windows 전용)
   - USB 장치 감지 (WMI 사용, Windows 전용)
   - 감지된 하드웨어 정보 데이터베이스 저장

2. **이벤트 로그 분석**
   - Windows 이벤트 로그(기본값: System) 분석
   - 사용자 지정 이벤트 소스 및 이벤트 ID 필터링
   - 지정된 이벤트 발생 횟수 카운팅
   - 이벤트 로그 데이터베이스 저장

3. **LLM 연동**
   - 임계값 이상의 이벤트 발생 시 Grok API 호출
   - 이벤트 로그에서 비정상적인 패턴 분석
   - 분석 결과 출력 및 경고 표시
   - 개선된 프롬프트로 정확한 분석 결과 제공

4. **환경 변수 및 설정 관리**
   - python-dotenv를 사용하여 .env 파일에서 API 키 로드
   - config.yaml 파일을 통한 중앙 설정 관리

5. **CLI 인터페이스**
   - 명령줄 인수를 통한 다양한 실행 모드 지원
   - 모니터링, 이벤트 내역 조회, DB 초기화 등 기능
   - 세부 옵션 제어 (LLM 비활성화, 기간 지정 등)

6. **데이터 저장 및 관리**
   - SQLite 데이터베이스 사용한 이벤트 및 하드웨어 정보 저장
   - 스캔 세션 관리 및 통계 기록
   - 과거 이벤트 조회 및 분석 기능

## 개선된 사항

### 1. 코드 구조 및 모듈화 ✅
- **개선 내용**: 
  - 코드를 여러 모듈로 분리 (src 폴더: monitor.py, llm_analyzer.py, utils.py 등)
  - 기능별 분리를 통한 유지보수성 개선
  - __init__.py 파일 추가로 패키지 구조화

### 2. 로깅 시스템 ✅
- **개선 내용**:
  - Python 로깅 모듈(logging) 사용
  - 로그 레벨 구분 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  - 파일 로깅 추가하여 결과 보존 (logs/app.log)
  - 로그 포맷 제어 가능

### 3. 설정 관리 ✅
- **개선 내용**:
  - 모든 설정이 config/config.yaml로 이동
  - 이벤트 로그, LLM, 로깅 등의 파라미터 외부화
  - 실행 시 설정 파일 로드 및 적용

### 4. 오류 처리 강화 ✅
- **개선 내용**:
  - 모든 함수에서 예외 처리 개선
  - 세부적인 예외 유형별 로깅 
  - 오류 발생 시 적절한 로깅 레벨 사용

### 5. LLM 분석 기능 개선 ✅
- **개선 내용**:
  - llm_analyzer.py로 LLM 연동 기능 분리
  - 비정상 패턴 키워드 설정 파일 관리
  - 응답 파싱 및 오류 처리 강화
  - 로그 데이터 전처리 기능 추가 (그룹화, 요약 등)
  - 개선된 프롬프트 작성으로 정확도 향상

### 6. CLI 인터페이스 개선 ✅
- **개선 내용**:
  - 명령줄 인수 처리 기능 추가 (argparse 사용)
  - 다양한 서브 명령어 지원 (monitor, history, initdb)
  - 유연한 옵션 설정 (기간, 제한, 출력 등)
  - 사용자 친화적인 도움말 메시지

### 7. 데이터 저장 및 분석 ✅
- **개선 내용**:
  - SQLite 데이터베이스 연동
  - 이벤트 로그, 하드웨어 정보, 세션 정보 저장
  - 데이터 조회 및 통계 기능
  - 세션 관리 및 요약 정보 생성

## 남은 개선 과제

### 1. 비동기 처리
- API 호출 및 장치 정보 수집에 비동기 처리 도입 
- 대용량 로그 처리 시 성능 최적화

### 2. 테스트 코드 추가
- 단위 테스트 구현 (pytest 사용)
- 모의 객체(mock)를 활용한 하드웨어 및 API 테스트
- CI/CD 파이프라인 구축

### 3. 사용자 인터페이스 확장
- 웹 인터페이스 구현 (Flask/FastAPI)
- 대시보드 및 시각화 기능 추가
- 원격 모니터링 및 알림 기능

### 4. 데이터 분석 고도화
- 머신러닝 기반 이상 탐지 기능
- 시계열 분석 및 이벤트 패턴 자동 감지
- 보고서 생성 기능 개선

## 완료된 작업
- ✅ 코드 모듈화 및 구조 개선
- ✅ 로깅 시스템 구현
- ✅ 설정 관리 개선 (config.yaml)
- ✅ 오류 처리 강화
- ✅ LLM 응답 분석 기능 개선
- ✅ CLI 인터페이스 구현
- ✅ 데이터베이스 연동 및 저장 기능 구현

## 진행 중인 작업
- 없음 (현재는 기능이 안정화된 상태)

## 해야 할 작업
- 비동기 처리 구현
- 테스트 코드 추가
- 웹 인터페이스 개발
- 머신러닝 기반 이상 탐지 기능 개발
