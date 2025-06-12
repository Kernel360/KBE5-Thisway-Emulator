"""
기본 로그 핸들러 추상 클래스
모든 로그 핸들러의 기본 인터페이스를 정의합니다.
"""

import abc
import queue
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional, Union

from models.emulator_data import GpsLogRequest, PowerLogRequest, GeofenceLogRequest


class BaseLogHandler(abc.ABC):
    """로그 처리를 위한 기본 추상 클래스"""

    def __init__(self, log_type: str, max_storage_hours: int = 24, backend_url: str = "http://localhost:8080",
                 use_auth: bool = False, auth_username: str = "", auth_password: str = ""):
        """
        로그 핸들러 초기화

        Args:
            log_type: 로그 타입 (예: 'gps', 'power', 'geofence')
            max_storage_hours: 최대 로그 보관 시간 (시간)
            backend_url: 백엔드 서버 URL
            use_auth: 인증 사용 여부
            auth_username: 인증 사용자명
            auth_password: 인증 비밀번호
        """
        # 해당 로그 타입에 대한 미전송 로그를 저장하는 큐 (MDN별)
        self.pending_logs = {}  # MDN -> Queue
        # 큐 액세스를 위한 락
        self.queue_lock = threading.Lock()
        # 최대 저장 시간 (기본 24시간)
        self.max_storage_hours = max_storage_hours
        # 백엔드 API 서버 URL
        self.backend_url = backend_url
        # 로그 타입
        self.log_type = log_type
        # 인증 정보
        self.use_auth = use_auth
        self.auth_username = auth_username
        self.auth_password = auth_password

    @property
    @abc.abstractmethod
    def backend_endpoint(self) -> str:
        """백엔드 API 엔드포인트"""
        pass

    def has_pending_logs(self, mdn: str) -> bool:
        """
        미전송 로그가 있는지 확인

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            bool: 미전송 로그 존재 여부
        """
        with self.queue_lock:
            return mdn in self.pending_logs and not self.pending_logs[mdn].empty()

    def count_pending_logs(self, mdn: str) -> int:
        """
        미전송 로그 개수 확인

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            int: 미전송 로그 개수
        """
        with self.queue_lock:
            if mdn not in self.pending_logs:
                return 0
            return self.pending_logs[mdn].qsize()

    def store_log(self, mdn: str, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> bool:
        """
        로그 데이터를 저장하고 즉시 전송 시도

        Args:
            mdn: 차량 번호(MDN)
            log_data: 저장할 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        # 즉시 전송 시도
        print(f"[INFO] {self.log_type} 로그 즉시 전송 시도 - MDN: {mdn}")
        success, error_msg = self.send_log_to_backend(log_data)

        if success:
            print(f"[SUCCESS] {self.log_type} 로그 즉시 전송 성공 - MDN: {mdn}")
            return True
        else:
            print(f"[WARNING] {self.log_type} 로그 즉시 전송 실패 - MDN: {mdn}, 오류: {error_msg}")
            print(f"[INFO] 실패한 로그를 대기열에 저장합니다 - MDN: {mdn}")

            # 전송 실패 시 큐에 저장
            with self.queue_lock:
                if mdn not in self.pending_logs:
                    self.pending_logs[mdn] = queue.Queue()

                log_entry = {
                    "data": log_data,
                    "timestamp": datetime.now(),
                    "retry_count": 0,
                    "log_type": self.log_type
                }

                self.pending_logs[mdn].put(log_entry)
                print(f"[DEBUG] {self.log_type} 로그 저장 성공 - MDN: {mdn}")
                print(f"[INFO] 현재 백엔드 전송 대기 로그 개수: {self.count_pending_logs(mdn)} - MDN: {mdn}")
                return True  # 저장은 성공했으므로 True 반환

    def send_log_to_backend(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> Tuple[bool, str]:
        """
        로그를 백엔드에 전송

        Args:
            log_data: 전송할 로그 데이터

        Returns:
            Tuple[bool, str]: (성공 여부, 오류 메시지)
        """
        import requests
        import json

        try:
            # 요청 URL 구성
            url = f"{self.backend_url}{self.backend_endpoint}"
            print(f"[백엔드 통신] 요청 URL: {url}")

            # JSON 변환
            log_json = log_data.dict()
            print(f"[백엔드 통신] 요청 로그 타입: {self.log_type}")
            print(f"[백엔드 통신] 요청 본문 길이: {len(str(log_json))} 바이트")

            # 로그 타입 결정 (시동 ON 또는 시동 OFF)
            log_type_str = ""
            if self.log_type == 'power':
                if log_json.get('onTime') and not log_json.get('offTime'):
                    log_type_str = "시동 ON"
                elif log_json.get('offTime'):
                    log_type_str = "시동 OFF"
                else:
                    log_type_str = "알 수 없음"
                print(f"[백엔드 통신] 전송 중인 로그 유형: {log_type_str}")

            # 디버그용으로 일부 필드 값만 출력
            debug_fields = {}
            if self.log_type == 'gps' and 'cList' in log_json and log_json['cList']:
                debug_fields = {
                    'mdn': log_json.get('mdn'),
                    'oTime': log_json.get('oTime'),
                    'cCnt': log_json.get('cCnt'),
                    'cList_count': len(log_json['cList']),
                    'first_point': log_json['cList'][0].dict() if hasattr(log_json['cList'][0], 'dict') else log_json['cList'][0] if log_json['cList'] else None
                }
            elif self.log_type == 'power':
                debug_fields = {
                    'mdn': log_json.get('mdn'),
                    'onTime': log_json.get('onTime'),
                    'offTime': log_json.get('offTime'),
                    'lat': log_json.get('lat'),
                    'lon': log_json.get('lon'),
                    'gcd': log_json.get('gcd'),
                    'sum': log_json.get('sum')
                }
            elif self.log_type == 'geofence':
                debug_fields = {
                    'mdn': log_json.get('mdn'),
                    'oTime': log_json.get('oTime'),
                    'geoGrpId': log_json.get('geoGrpId'),
                    'geoPId': log_json.get('geoPId'),
                    'evtVal': log_json.get('evtVal'),
                    'lat': log_json.get('lat'),
                    'lon': log_json.get('lon'),
                    'gcd': log_json.get('gcd'),
                    'sum': log_json.get('sum')
                }
            print(f"[백엔드 통신] 요청 주요 필드: {debug_fields}")

            # 전체 JSON 데이터 출력 (디버깅용)
            if self.log_type == 'power':
                print(f"[백엔드 통신] {log_type_str} 전체 JSON 데이터: {json.dumps(log_json, indent=2)}")

            # 디버그용 로그 출력 (로그 타입에 따라 다른 정보 출력)
            self._print_debug_log(log_data)

            # 요청 헤더
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'ThiswayVehicleEmulator/1.0'
            }

            # 인증 정보 제거 - 인증 없이 요청
            auth = None

            # 요청 전송 시도 기록
            print(f"[백엔드 통신] {self.log_type} 로그 전송 시도...")
            print(f"[백엔드 통신] 인증 정보 사용하지 않음 (open access)")

            # POST 요청 전송
            response = requests.post(
                url, 
                data=json.dumps(log_json), 
                headers=headers,
                auth=auth,
                timeout=10  # 타임아웃 10초
            )

            # 응답 처리
            print(f"[백엔드 통신] 응답 상태코드: {response.status_code}")
            print(f"[백엔드 통신] 응답 헤더: {dict(response.headers)}")

            if response.status_code in [200, 201]:
                try:
                    response_data = response.json()
                    print(f"[백엔드 통신] 응답 본문: {response_data}")

                    if response_data.get("code") == "000" or response_data.get("rstCd") == "000":
                        print(f"[백엔드 통신] 요청 성공: {self.log_type} 로그")
                        return True, "Success"
                    else:
                        # 오류 메시지 필드도 두 가지 형식 모두 확인
                        error_message = response_data.get('message') or response_data.get('rstMsg', '알 수 없는 오류')
                        error_code = response_data.get('code') or response_data.get('rstCd', 'N/A')
                        error_msg = f"백엔드 오류: {error_message} (Code: {error_code})"
                        print(f"[오류] {error_msg}")
                        return False, error_msg
                except ValueError as e:
                    error_msg = f"JSON 응답 파싱 오류: {str(e)}, 응답 본문: {response.text[:200]}"
                    print(f"[오류] {error_msg}")
                    return False, error_msg
            else:
                error_msg = f"백엔드 응답 오류: HTTP {response.status_code} - {response.text[:200]}"
                print(f"[오류] {error_msg}")
                # 401 오류 처리 제거 - 인증을 사용하지 않으므로 필요없음
                return False, error_msg

        except requests.exceptions.ConnectionError as e:
            error_msg = f"서버 연결 오류: {str(e)}"
            print(f"[연결 오류] 백엔드 서버({self.backend_url})에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요.")
            print(f"[연결 오류] 상세 오류 정보: {str(e)}")

            # 로그 타입 확인 (시동 OFF 로그인 경우 더 자세한 정보 출력)
            if self.log_type == 'power' and isinstance(log_data, PowerLogRequest) and log_data.offTime:
                print(f"[중요] 시동 OFF 로그 전송 실패 - MDN: {log_data.mdn}, onTime: {log_data.onTime}, offTime: {log_data.offTime}")
                print(f"[중요] 백엔드 서버 URL: {self.backend_url}{self.backend_endpoint}")
                print(f"[중요] 백엔드 서버가 실행 중인지 확인하세요. 현재 설정된 URL: {self.backend_url}")

            return False, error_msg
        except requests.exceptions.Timeout as e:
            error_msg = f"요청 시간 초과: {str(e)}"
            print(f"[시간 초과] 백엔드 서버가 응답하지 않습니다 (10초 타임아웃)")
            print(f"[시간 초과] 상세 오류 정보: {str(e)}")

            # 로그 타입 확인 (시동 OFF 로그인 경우 더 자세한 정보 출력)
            if self.log_type == 'power' and isinstance(log_data, PowerLogRequest) and log_data.offTime:
                print(f"[중요] 시동 OFF 로그 전송 시간 초과 - MDN: {log_data.mdn}, onTime: {log_data.onTime}, offTime: {log_data.offTime}")

            return False, error_msg
        except requests.exceptions.RequestException as e:
            error_msg = f"요청 오류: {str(e)}"
            print(f"[오류] {error_msg}")
            print(f"[오류] 상세 오류 정보: {str(e)}")

            # 로그 타입 확인 (시동 OFF 로그인 경우 더 자세한 정보 출력)
            if self.log_type == 'power' and isinstance(log_data, PowerLogRequest) and log_data.offTime:
                print(f"[중요] 시동 OFF 로그 전송 요청 오류 - MDN: {log_data.mdn}, onTime: {log_data.onTime}, offTime: {log_data.offTime}")

            return False, error_msg
        except Exception as e:
            error_msg = f"예상치 못한 오류: {str(e)}"
            print(f"[오류] {error_msg}")
            import traceback
            print(f"[오류] 상세 스택 트레이스: {traceback.format_exc()}")

            # 로그 타입 확인 (시동 OFF 로그인 경우 더 자세한 정보 출력)
            if self.log_type == 'power' and isinstance(log_data, PowerLogRequest) and log_data.offTime:
                print(f"[중요] 시동 OFF 로그 전송 중 예상치 못한 오류 - MDN: {log_data.mdn}, onTime: {log_data.onTime}, offTime: {log_data.offTime}")

            return False, error_msg

    def process_all_pending_logs(self) -> int:
        """
        모든 MDN에 대한 미전송 로그 처리

        Returns:
            int: 총 처리된 로그 수
        """
        total_processed = 0

        # 현재 큐에 있는 모든 MDN 목록 복사
        with self.queue_lock:
            mdn_list = list(self.pending_logs.keys())

        # 각 MDN에 대한 로그 처리
        for mdn in mdn_list:
            processed = self.process_pending_logs(mdn)
            total_processed += processed

        return total_processed

    def get_pending_logs(self, mdn: str) -> list:
        """
        특정 MDN에 대한 미전송 로그 목록 조회

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            list: 미전송 로그 목록
        """
        logs = []
        with self.queue_lock:
            if mdn in self.pending_logs:
                # 큐의 내용을 리스트로 변환 (큐를 비우지 않고 복사)
                temp_queue = queue.Queue()
                while not self.pending_logs[mdn].empty():
                    log_entry = self.pending_logs[mdn].get()
                    logs.append(log_entry)
                    temp_queue.put(log_entry)

                # 원래 큐 복원
                self.pending_logs[mdn] = temp_queue

        return logs

    def process_pending_logs(self, mdn: str) -> int:
        """
        특정 MDN에 대한 미전송 로그 처리

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            int: 처리된 로그 수
        """
        processed_count = 0

        with self.queue_lock:
            if mdn not in self.pending_logs or self.pending_logs[mdn].empty():
                return 0

            # 큐에서 항목을 하나씩 처리
            temp_queue = queue.Queue()
            current_time = datetime.now()

            while not self.pending_logs[mdn].empty():
                log_entry = self.pending_logs[mdn].get()
                retry_count = log_entry.get("retry_count", 0)

                print(f"[DEBUG] {self.log_type} 로그 처리 시도 - MDN: {mdn}, 재시도: {retry_count}")

                # 오래된 로그는 삭제
                time_diff = current_time - log_entry["timestamp"]
                if time_diff >= timedelta(hours=self.max_storage_hours):
                    print(f"[INFO] {self.log_type} 로그 최대 보관 시간 초과 - 폐기합니다. MDN: {mdn}")
                    continue

                # 로그 전송 시도
                success, error_msg = self.send_log_to_backend(log_entry["data"])
                processed_count += 1

                if success:
                    print(f"[INFO] {self.log_type} 로그 전송 성공 - MDN: {mdn}")
                    print(f"[DEBUG] 성공한 로그는 더 이상 보관하지 않습니다 (자동 삭제) - MDN: {mdn}")
                else:
                    print(f"[ERROR] {self.log_type} 로그 전송 실패 - MDN: {mdn}, 오류: {error_msg}")
                    # 재시도 횟수 증가
                    log_entry["retry_count"] = retry_count + 1
                    # 전송 실패한 로그는 다시 큐에 넣기
                    print(f"[DEBUG] 실패한 로그 재시도 대기열에 등록 - MDN: {mdn}, 재시도: {log_entry['retry_count']}")
                    temp_queue.put(log_entry)

            # 전송 실패한 로그만 다시 저장
            if not temp_queue.empty():
                self.pending_logs[mdn] = temp_queue
            else:
                del self.pending_logs[mdn]

        return processed_count

    @abc.abstractmethod
    def _print_debug_log(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> None:
        """로그 타입에 맞는 디버그 정보 출력 (추상 메서드)"""
        pass
