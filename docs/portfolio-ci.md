# PR CI와 검증 범위

2026-09-08, 기준8d017d6. 원 팀 Emulator 위의 AI 지원 개인 현대화다. 로컬 장치 credential·재시도·시간 묶음 회귀를 PR에서 반복하도록 workflow를 추가했다.

선택: secrets 없는 pull_request/workflow_dispatch, contents:read,10분 timeout, Python3.11과 requirements.txt 설치. unittest discover -s tests -v만 실행한다. 루트 test_emulator.py는 외부 전송 가능한 수동 스크립트로 CI에 넣지 않는다.

첫 시스템 Python3.14 실행은 pydantic 미설치로 import 오류2건이었다. 전용 Python3.11.16 환경에서 pydantic2.4.2, python-dotenv1.0.0, requests2.31.0을 확인하고32개 테스트를 성공시켰다. 실제 외부 backend 전송·운영 검증 또는 GitHub runner green을 주장하지 않는다.

재현: Python3.11 venv 생성→python -m pip install -r requirements.txt→python -m unittest discover -s tests -v. CI와 동일 핵심 명령이다.

면접 질문: 수동 스크립트를 왜 discover하지 않나(외부 부작용)? Python 버전을 왜 고정하나(의존성 호환·재현성)? 테스트가 무엇을 증명하나(로컬 HTTP 계약과 queue 상태, 실제 운영은 별도)? AI가 CI 작성·실행을 지원했으며 원 팀 기여와 개인 현대화를 구분한다.
