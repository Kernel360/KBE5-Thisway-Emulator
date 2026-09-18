# Thisway 에뮬레이터

차량 GPS 데이터를 생성하고 백엔드 서버로 전송하는 경량 에뮬레이터입니다.

## 개요

이 에뮬레이터는 차량용 실제와 유사한 GPS 데이터를 생성하여 백엔드 서버로 전송합니다. 각각 고유한 모바일 기기 번호(MDN)를 가진 여러 차량을 동시에 시뮬레이션할 수 있습니다.

## 설치

1. 저장소 복제
2. 필요한 종속성 설치:

```bash
pip install -r requirements.txt
```

## 사용법

에뮬레이터는 명령줄 모드와 대화형 모드 두 가지 방식으로 사용할 수 있습니다.

### 명령줄 모드

특정 MDN에 대한 에뮬레이터 시작:

```bash
python main.py start <mdn>
```

에뮬레이터 중지:

```bash
python main.py stop
```

GPS 로그 데이터 생성:

```bash
python main.py generate [--realtime] [--no-store]
```

대기 중인 로그 확인:

```bash
python main.py pending
```

현재 에뮬레이터 상태 확인:

```bash
python main.py status
```

### 대화형 모드

대화형 모드에서 에뮬레이터 실행:

```bash
python main.py interactive
```

대화형 모드에서는 다음 명령어를 사용할 수 있습니다:

- `start <mdn>` - 지정된 MDN에 대한 에뮬레이터 시작
- `stop` - 현재 에뮬레이터 중지
- `generate [realtime] [nostore]` - GPS 로그 데이터 생성
- `pending` - 현재 에뮬레이터의 대기 중인 로그 확인
- `status` - 현재 에뮬레이터 상태 표시
- `help` - 도움말 메시지 표시
- `exit` 또는 `quit` - 프로그램 종료

## 설정

에뮬레이터는 `config.py`에서 다음 설정을 사용합니다:

- `DEFAULT_LATITUDE` 및 `DEFAULT_LONGITUDE` - 새 에뮬레이터의 기본 위치
- `API_HOST` 및 `API_PORT` - 백엔드 서버의 호스트 및 포트

이러한 설정은 `config.py`에서 수정하거나 환경 변수를 사용하여 설정할 수 있습니다.

## 예시

```bash
# 대화형 모드에서 에뮬레이터 시작
python main.py interactive

# 대화형 모드에서
> start 1234567890
MDN: 1234567890에 대한 에뮬레이터 시작됨

> generate realtime
실시간 데이터 수집을 시작했습니다. 로그는 60초마다 생성됩니다.

> status
에뮬레이터 상태: 활성
MDN: 1234567890
위치: (37.5665, 126.9780)

> stop
에뮬레이터 1234567890를 중지합니다.
에뮬레이터는 GPS 주기정보 전송 종료 시 자동으로 중지됩니다.

> exit
종료 중...
```

