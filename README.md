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

백엔드 주소는 `CONFIG_PATH`가 가리키는 JSON 파일(미설정 시 `config.json`)의
`backend_url`을 먼저 사용합니다. 파일에서 주소를 얻지 못하면 `BACKEND_URL` 환경 변수,
이후 `http://localhost:8080` 순서로 선택합니다. 설정 파일에 `backend_url`이 있으면
`BACKEND_URL`보다 우선합니다.

시작 시에도 telemetry 전송과 같은 URL 검증을 먼저 적용합니다. 외부 주소는 HTTPS,
loopback은 HTTP를 허용하고 사용자명·비밀번호·query·fragment·하위 경로가 포함된 주소는
연결 전에 거부합니다. URL 원문과 HTTP 예외 원문은 초기화 로그에 출력하지 않습니다.
초기 연결 확인은 공개 `GET /api/health`를 사용하며 redirect를 따라가지 않습니다.
이 확인은 서버의 응답 여부만 확인하고 장치 인증 성공을 증명하지 않습니다.

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


## 장치 인증 (2026-09-07)

GPS/Power/Geofence 전송은 `X-Device-Id`와 `X-Device-Key`를 요구합니다.
`device_id`는 백엔드 Emulator의 DB ID이며 payload의 `did`와 다릅니다.
회사 관리자가 발급한 키를 저장소 밖 JSON 파일에 MDN별로 저장합니다. 예시는 실제 키가 아닙니다.

```json
{"실제 MDN": {"device_id": 123, "key": "발급 응답의 key 전체"}}
```

```bash
chmod 600 "$HOME/.config/thisway/device-credentials.json"
export DEVICE_CREDENTIALS_FILE="$HOME/.config/thisway/device-credentials.json"
```

파일 누락/잘못된 권한/MDN 누락은 전송하지 않습니다. 새 로그 전송은 파일을 읽어 키 교체를 반영합니다.
외부 서버는 HTTPS가 필요하고 개발용 loopback HTTP만 허용합니다. redirect를 따라가지 않으며
원문 키는 telemetry body/실패 큐/오류 로그에 저장하지 않습니다. 환경 변수는 실행 전에 설정합니다.
401은 성공으로 처리하지 않고 실패 큐에 보존합니다. 실패 큐는 최초 전송에 사용한 MDN·`device_id`·
credential fingerprint를 고정하고 원문 키는 저장하지 않습니다. fingerprint도 `repr`나 재전송 로그에 출력하지 않습니다.

실패 큐의 재전송 정책은 다음과 같습니다.

- 현재 MDN·device ID·fingerprint가 모두 같으면 같은 credential snapshot으로 재시도합니다.
- 키나 device ID가 바뀌거나 현재 credential을 확인할 수 없으면 `paused`로 보존하고 HTTP를 보내지 않습니다.
  같은 차량의 정상 key rotation이어도 backlog에는 보수적으로 이 정책을 적용합니다.
- 처음부터 credential이 없었거나 기존 queue에 source identity가 없으면 `paused`로 보존합니다.
  나중에 추가한 키로 원래 소속을 추정하지 않습니다.
- 한 번 `paused`가 되면 키가 복원되어도 자동 재개하지 않습니다. `get_pending_logs()`에서
  `retry_state`와 `pause_reason`을 확인할 수 있고 일반 로그에는 고정된 검토 사유만 남깁니다.
- 정상 `pending`에는 기존 보관 기간이 적용됩니다. 검토가 필요한 `paused` 항목은 기간이 지나도
  자동 폐기하지 않지만, 모든 큐는 메모리 기반이므로 프로세스 종료 시 유실되고 디스크에 영구 보존되지 않습니다.

장치를 다른 차량에 재연결하기 전 backlog를 점검해야 합니다. 원래 소속을 확인한 별도 승인 재처리가
필요하며, 이 구현은 paused 데이터에 새 연결 키를 강제로 붙이거나 자동 resume하는 기능을 제공하지 않습니다.
원본 packet은 enqueue 시 복사하여 이후 객체 변경과 무관하게 보존하고 이벤트 시간을 다시 쓰지 않습니다.

Python 3.11 venv에서 requirements.txt 설치 후 다음 검증을 실행합니다.

```bash
python -m unittest discover -s tests -v
```

이 테스트는 실제 localhost HTTP 전송을 검증합니다. BE의 `emulatorClientTest`는 임시 Boot/MySQL까지 연결합니다.
기존 `test_emulator.py`는 실시간 생성/전송 부작용이 있는 수동 스크립트로 이번 회귀 명령과 다릅니다.
설계·검증·한계는 sibling BE의 `docs/portfolio/work-logs/2026-09-07-device-ingestion-authentication.md`에 기록했습니다.

수집 요청은 전송 시도마다 `X-Request-Id`(UUID v4), `X-Request-Timestamp`(epoch seconds)를 자동 생성합니다. 서버와 시계 차이는 5분 이내여야 하며 원래 `oTime`은 바꾸지 않습니다. 서버의 기본 제한은 장치별 120회/60초, 실제 본문 256 KiB입니다. 동일 source identity가 확인된 retry만 새 HTTP 시도로 보내고 observation 중복 처리는 서버 DB가 담당합니다.
backlog 소속 보호와 검증은 sibling BE의 `docs/portfolio/work-logs/2026-09-07-emulator-backlog-binding.md`에 기록했습니다.

2026-09-12 초기화 URL 보호·health 경로 수정과 운영/CI 감사는 sibling BE의
`docs/portfolio/work-logs/2026-09-12-emulator-ops-audit.md`에 기록했습니다.
