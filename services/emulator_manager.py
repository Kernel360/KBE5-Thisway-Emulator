import random
import sys
import time
import threading
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple
from models.emulator_data import VehicleData

class EmulatorManager:
    """
    단일 에뮬레이터 상태 관리 클래스
    - 에뮬레이터 시작/중지 관리
    - 에뮬레이터 상태 정보 관리
    - 위치, 승객, 시간 등의 데이터 관리
    """

    def __init__(self, mdn: str = "01012345678"):
        # 고정 MDN 설정
        self.mdn = mdn

        # 에뮬레이터 정보 저장
        self.terminal_id = f"TERM-{mdn[-4:]}"
        self.manufacture_id = 6
        self.packet_version = 5
        self.device_id = 1
        self.device_firmware_version = "1.0.0"

        # 초기 위치 - 서울시 중심부 근처
        self.last_latitude = 37.5665 + random.uniform(-0.01, 0.01)
        self.last_longitude = 126.9780 + random.uniform(-0.01, 0.01)
        self.is_active = False
        self.last_update = datetime.now()
        self.accumulated_distance = 0  # 누적 주행거리 (미터)

        # MDN별 누적 주행거리 저장을 위한 딕셔너리
        self.mdn_accumulated_distances = {}

        # 마지막 위치 캐시 (시동 OFF 시 마지막 위치 저장)
        self.last_position = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }

        # 마지막 GPS 주기정보 데이터 포인트 저장
        self.last_gps_batch_data = None

        # 실시간 데이터 수집을 위한 타이머 스레드 관리
        self.data_timer = None
        self.collecting_data = []
        self.data_callback = None
        self.stop_event = None

        # 여러 에뮬레이터의 데이터 타이머 관리를 위한 딕셔너리
        self.data_timers = {}

        # 백엔드 API 설정
        self.backend_url = "http://localhost:8080/api/vehicles"

        # 이전 버전과의 호환성을 위한 active_emulators 딕셔너리
        self.active_emulators = {self.mdn: self.get_emulator_dict()}

        # 여러 에뮬레이터의 마지막 위치 저장을 위한 딕셔너리
        self.last_positions = {
            self.mdn: {
                "latitude": self.last_latitude,
                "longitude": self.last_longitude,
                "timestamp": datetime.now()
            }
        }

        # 카카오 API 경로 데이터 저장
        self.kakao_route_points = []  # 카카오 API에서 가져온 경로 포인트 목록
        self.current_route_index = 0  # 현재 사용 중인 경로 포인트 인덱스

    def start_emulator(self, terminal_id: str = None, manufacture_id: int = None, 
                        packet_version: int = None, device_id: int = None, device_firmware_version: str = None) -> bool:
        """
        에뮬레이터 데이터 생성 시작

        Args:
            terminal_id: 터미널 아이디 (차량관제는 'A001'로 고정)
            manufacture_id: 제조사 아이디 (CNSLink는 '6' 값 사용)
            packet_version: 패킷 버전 (M2M 버전이 5이므로 '5'로 고정)
            device_id: 디바이스 아이디 (GPS로만 운영함으로 '1'로 고정)
            device_firmware_version: 디바이스 펌웨어 버전
        """
        # 초기 위치 - 서울시 중심부 근처
        self.last_latitude = 37.5665 + random.uniform(-0.01, 0.01)
        self.last_longitude = 126.9780 + random.uniform(-0.01, 0.01)

        # 에뮬레이터 데이터 업데이트
        if terminal_id:
            self.terminal_id = terminal_id
        if manufacture_id:
            self.manufacture_id = manufacture_id
        if packet_version:
            self.packet_version = packet_version
        if device_id:
            self.device_id = device_id
        if device_firmware_version:
            self.device_firmware_version = device_firmware_version

        self.is_active = True
        self.last_update = datetime.now()

        # 새 MDN인 경우에만 누적 거리를 초기화
        if self.mdn not in self.mdn_accumulated_distances:
            self.mdn_accumulated_distances[self.mdn] = 0

        # 저장된 누적 거리 사용
        self.accumulated_distance = self.mdn_accumulated_distances[self.mdn]

        # 마지막 위치 저장
        self.last_position = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }

        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.active_emulators = {self.mdn: self.get_emulator_dict()}

        # 마지막 위치 정보 업데이트
        self.last_positions[self.mdn] = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }

        # 백엔드 powerOn 업데이트 제거 - 로그만 남김
        print(f"[INFO] 차량 에뮬레이터 시작: MDN={self.mdn}")

        return True

    def stop_emulator(self, mdn: str = None) -> bool:
        """
        에뮬레이터 데이터 생성 중지

        Args:
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)
        """
        # MDN이 지정되지 않은 경우 현재 에뮬레이터의 MDN 사용
        if mdn is None:
            mdn = self.mdn

        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn != self.mdn:
            print(f"[ERROR] 현재 에뮬레이터의 MDN({self.mdn})과 요청된 MDN({mdn})이 일치하지 않습니다.")
            return False
        # 마지막 위치 저장 (시동 OFF 시 사용)
        self.last_position = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }

        # 마지막 위치 정보 업데이트
        self.last_positions[self.mdn] = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }

        # 에뮬레이터 비활성화 처리
        self.is_active = False

        # 실시간 데이터 생성 타이머 중지
        self.stop_realtime_data_collection()

        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.active_emulators = {self.mdn: self.get_emulator_dict()}

        # 백엔드 powerOff 업데이트 제거 - 로그만 남김
        print(f"[INFO] 차량 에뮬레이터 중지: MDN={self.mdn}")

        # 프로그램 정상 종료를 위해 sys.exit(0) 대신 True 반환
        print(f"[INFO] 에뮬레이터가 중지되었습니다. 정상적인 종료 프로세스를 진행합니다.")

        return True

    def start_realtime_data_collection(self, mdn: str = None, callback: Callable[[str, list], None] = None, 
                                  interval_sec: float = 1.0, batch_size: int = 60, send_interval_sec: float = 60.0):
        """
        실시간 GPS 데이터 생성 시작

        Args:
            mdn: 차량 번호(MDN), 기본값은 None (현재 에뮬레이터의 MDN 사용)
            callback: 배치가 채워졌을 때 호출될 함수 (mdn, data_list)
            interval_sec: 데이터 생성 간격 (초)
            batch_size: 데이터 수집 배치 크기
            send_interval_sec: 데이터 전송 주기 (초)
        """
        # MDN이 지정되지 않은 경우 현재 에뮬레이터의 MDN 사용
        if mdn is None:
            mdn = self.mdn

        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn != self.mdn:
            print(f"[ERROR] 현재 에뮬레이터의 MDN({self.mdn})과 요청된 MDN({mdn})이 일치하지 않습니다.")
            return False

        # 기존 타이머가 있다면 먼저 중지
        self.stop_realtime_data_collection(mdn)

        # 새로운 데이터 수집 시작
        if self.is_active:
            self.collecting_data = []
            self.data_callback = callback

            # 타이머 스레드 생성
            self.stop_event = threading.Event()
            self.data_timer = threading.Thread(
                target=self._data_collection_worker,
                args=(interval_sec, batch_size, send_interval_sec, self.stop_event),
                daemon=True
            )

            # 타이머 시작 및 data_timers에 저장
            self.data_timer.start()
            self.data_timers[mdn] = self.data_timer

            print(f"Started real-time data collection for MDN: {mdn}")
            return True
        return False

    def stop_realtime_data_collection(self, mdn: str = None) -> bool:
        """
        실시간 데이터 수집 중지

        Args:
            mdn: 차량 번호(MDN), 기본값은 None (현재 에뮬레이터의 MDN 사용)

        Returns:
            bool: 중지 성공 여부
        """
        # MDN이 지정되지 않은 경우 현재 에뮬레이터의 MDN 사용
        if mdn is None:
            mdn = self.mdn

        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn != self.mdn:
            print(f"[ERROR] 현재 에뮬레이터의 MDN({self.mdn})과 요청된 MDN({mdn})이 일치하지 않습니다.")
            return False

        # data_timers에서 해당 MDN의 타이머 제거
        if mdn in self.data_timers:
            del self.data_timers[mdn]

        if self.data_timer and self.stop_event:
            self.stop_event.set()

            # 현재 스레드가 data_timer 스레드인지 확인
            current_thread = threading.current_thread()
            if current_thread != self.data_timer:
                # 다른 스레드에서 호출된 경우에만 join 시도
                self.data_timer.join(timeout=2.0)
            else:
                print(f"[INFO] 데이터 수집 스레드 내에서 중지 요청됨 - join 건너뜀")

            self.data_timer = None

            # 남은 데이터 처리
            if self.collecting_data and self.data_callback and callable(self.data_callback):
                # 마지막 데이터 포인트 저장 (추가된 코드)
                if self.collecting_data:
                    self.last_gps_batch_data = self.collecting_data[-1]
                    print(f"[DEBUG] 남은 데이터의 마지막 GPS 주기정보 저장 - MDN: {self.mdn}, 좌표: ({self.last_gps_batch_data['latitude']}, {self.last_gps_batch_data['longitude']})")

                self.data_callback(self.mdn, self.collecting_data)
                self.collecting_data = []

            return True
        return False

    def stop_realtime_data_collection_all(self):
        """실시간 데이터 수집 타이머 중지"""
        if hasattr(self, 'data_timer') and self.data_timer:
            print("[INFO] 실시간 데이터 수집 타이머 중지")
            self.stop_realtime_data_collection(self.mdn)
            return True
        return False

    def update_position(self):
        """
        에뮬레이터 위치 업데이트 (카카오 API 경로 데이터 사용)
        """
        print(f"[DEBUG] 위치 업데이트 시작 - MDN: {self.mdn}, 활성 상태: {self.is_active}")

        if not self.is_active:
            print(f"[DEBUG] 에뮬레이터가 비활성 상태입니다. 위치 업데이트를 건너뜁니다 - MDN: {self.mdn}")
            return

        # 현재 좌표값 확인
        print(f"[DEBUG] 현재 좌표: ({self.last_latitude}, {self.last_longitude}) - MDN: {self.mdn}")

        # 좌표가 비정상적으로 작은 경우 (서울 좌표로 초기화)
        if abs(self.last_latitude) < 1.0:  # 위도가 1도보다 작으면 비정상으로 판단
            print(f"[WARNING] 비정상 좌표 감지: ({self.last_latitude}, {self.last_longitude}) - MDN: {self.mdn}")
            self.last_latitude = 37.5665
            self.last_longitude = 126.9780
            print(f"[INFO] 위치 초기화: {self.mdn} - 서울 좌표로 재설정 (37.5665, 126.9780)")

        # 카카오 API 경로 데이터 확인
        has_route_data = self.kakao_route_points and len(self.kakao_route_points) > 0
        print(f"[DEBUG] 카카오 API 경로 데이터 상태: {'있음' if has_route_data else '없음'}, 포인트 수: {len(self.kakao_route_points) if has_route_data else 0} - MDN: {self.mdn}")

        # 카카오 API 경로 데이터가 있는 경우 해당 데이터 사용
        if has_route_data:
            # 현재 인덱스 확인
            print(f"[DEBUG] 현재 경로 인덱스: {self.current_route_index}, 전체 포인트 수: {len(self.kakao_route_points)} - MDN: {self.mdn}")

            # 현재 인덱스가 유효한지 확인
            if self.current_route_index < len(self.kakao_route_points):
                # 현재 경로 포인트 가져오기
                current_point = self.kakao_route_points[self.current_route_index]
                print(f"[DEBUG] 현재 경로 포인트: {current_point} - MDN: {self.mdn}")

                # 이전 위치 저장 (디버깅용)
                prev_lat = self.last_latitude
                prev_lon = self.last_longitude

                # 위치 업데이트
                self.last_latitude = current_point["latitude"]
                self.last_longitude = current_point["longitude"]
                print(f"[DEBUG] 위치 업데이트 - 이전: ({prev_lat}, {prev_lon}), 새 위치: ({self.last_latitude}, {self.last_longitude}) - MDN: {self.mdn}")

                # 다음 포인트로 인덱스 이동
                self.current_route_index += 1
                print(f"[DEBUG] 다음 경로 인덱스로 이동: {self.current_route_index} - MDN: {self.mdn}")

                # 모든 경로 포인트를 사용한 경우 에뮬레이터 중지 및 프로그램 종료
                if self.current_route_index >= len(self.kakao_route_points):
                    print(f"[INFO] 모든 경로 포인트를 사용했습니다. 에뮬레이터를 중지합니다 - MDN: {self.mdn}")

                    # 남은 데이터 처리 (에뮬레이터 중지 전에 수행)
                    if self.collecting_data and self.data_callback and callable(self.data_callback):
                        # 마지막 데이터 포인트 저장 (추가된 코드)
                        if self.collecting_data:
                            self.last_gps_batch_data = self.collecting_data[-1]
                            print(f"[DEBUG] 남은 데이터의 마지막 GPS 주기정보 저장 - MDN: {self.mdn}, 좌표: ({self.last_gps_batch_data['latitude']}, {self.last_gps_batch_data['longitude']})")

                        print(f"[INFO] 남은 데이터 처리 중 - {len(self.collecting_data)}개 데이터 포인트 - MDN: {self.mdn}")
                        self.data_callback(self.mdn, self.collecting_data)
                        self.collecting_data = []

                    # 로그 전송을 위한 대기 시간 추가
                    print(f"[INFO] 목적지에 도달했습니다. 로그 전송을 위해 잠시 대기합니다 - MDN: {self.mdn}")
                    import time
                    time.sleep(2)  # 2초 대기

                    # 미전송 로그 처리
                    from services.data_generator import data_generator
                    pending_logs = data_generator.log_storage_manager.count_pending_logs()
                    total_pending = sum(pending_logs.values())
                    if total_pending > 0:
                        print(f"[INFO] 종료 전 미전송 로그 처리 시작 - MDN: {self.mdn}")
                        data_generator.log_storage_manager.process_pending_logs()

                    # GPS 로그 전송 후 시동 OFF 로그 생성 및 전송
                    print(f"[INFO] GPS 로그 전송 완료. 시동 OFF 로그 생성 및 전송 시작 - MDN: {self.mdn}")
                    data_generator.stop_vehicle(self.mdn)

                    # 시동 OFF 로그 전송을 위한 추가 대기
                    print(f"[INFO] 시동 OFF 로그 전송을 위해 잠시 대기합니다 - MDN: {self.mdn}")
                    import time
                    time.sleep(1)  # 1초 대기

                    # 시동 OFF 로그 전송 확인
                    pending_logs = data_generator.log_storage_manager.count_pending_logs()
                    power_pending = pending_logs.get('power', 0)
                    if power_pending > 0:
                        print(f"[INFO] 시동 OFF 로그 전송 시도 중 - 대기 중인 전원 로그: {power_pending}개")
                        data_generator.log_storage_manager.process_pending_logs()

                    # 에뮬레이터 비활성화
                    self.is_active = False
                    if self.stop_event:
                        self.stop_event.set()

                    # 에뮬레이터 중지 (스레드 안전하게)
                    self.stop_emulator()

                    print(f"[INFO] 목적지에 도달했습니다. 프로그램을 종료합니다 - MDN: {self.mdn}")

                    # 종료 처리를 위한 함수 정의
                    def cleanup_and_exit():
                        print(f"[INFO] 프로그램 종료 전 정리 작업 수행 중...")
                        # 여기에 필요한 정리 작업 코드 추가 가능

                    # 정리 함수 등록 (이미 등록되어 있다면 다시 등록할 필요 없음)
                    import atexit
                    atexit.register(cleanup_and_exit)

                    # 프로그램 종료 - 자동으로 등록된 모든 atexit 핸들러가 호출됨
                    import sys
                    sys.exit(0)
            else:
                # 인덱스가 범위를 벗어난 경우 에뮬레이터 중지 및 프로그램 종료
                print(f"[WARNING] 경로 인덱스가 범위를 벗어났습니다: {self.current_route_index} >= {len(self.kakao_route_points)} - MDN: {self.mdn}")
                print(f"[INFO] 모든 경로 포인트를 사용했습니다. 에뮬레이터를 중지합니다 - MDN: {self.mdn}")

                # 남은 데이터 처리 (에뮬레이터 중지 전에 수행)
                if self.collecting_data and self.data_callback and callable(self.data_callback):
                    # 마지막 데이터 포인트 저장 (추가된 코드)
                    if self.collecting_data:
                        self.last_gps_batch_data = self.collecting_data[-1]
                        print(f"[DEBUG] 남은 데이터의 마지막 GPS 주기정보 저장 - MDN: {self.mdn}, 좌표: ({self.last_gps_batch_data['latitude']}, {self.last_gps_batch_data['longitude']})")

                    print(f"[INFO] 남은 데이터 처리 중 - {len(self.collecting_data)}개 데이터 포인트 - MDN: {self.mdn}")
                    self.data_callback(self.mdn, self.collecting_data)
                    self.collecting_data = []

                # 로그 전송을 위한 대기 시간 추가
                print(f"[INFO] 목적지에 도달했습니다. 로그 전송을 위해 잠시 대기합니다 - MDN: {self.mdn}")
                import time
                time.sleep(2)  # 2초 대기

                # 미전송 로그 처리
                from services.data_generator import data_generator
                pending_logs = data_generator.log_storage_manager.count_pending_logs()
                total_pending = sum(pending_logs.values())
                if total_pending > 0:
                    print(f"[INFO] 종료 전 미전송 로그 처리 시작 - MDN: {self.mdn}")
                    data_generator.log_storage_manager.process_pending_logs()

                # GPS 로그 전송 후 시동 OFF 로그 생성 및 전송
                print(f"[INFO] GPS 로그 전송 완료. 시동 OFF 로그 생성 및 전송 시작 - MDN: {self.mdn}")
                data_generator.stop_vehicle(self.mdn)

                # 시동 OFF 로그 전송을 위한 추가 대기
                print(f"[INFO] 시동 OFF 로그 전송을 위해 잠시 대기합니다 - MDN: {self.mdn}")
                import time
                time.sleep(1)  # 1초 대기

                # 시동 OFF 로그 전송 확인
                pending_logs = data_generator.log_storage_manager.count_pending_logs()
                power_pending = pending_logs.get('power', 0)
                if power_pending > 0:
                    print(f"[INFO] 시동 OFF 로그 전송 시도 중 - 대기 중인 전원 로그: {power_pending}개")
                    data_generator.log_storage_manager.process_pending_logs()

                # 에뮬레이터 비활성화
                self.is_active = False
                if self.stop_event:
                    self.stop_event.set()

                # 에뮬레이터 중지 (스레드 안전하게)
                self.stop_emulator()

                print(f"[INFO] 목적지에 도달했습니다. 프로그램을 종료합니다 - MDN: {self.mdn}")

                # 종료 처리를 위한 함수 정의
                def cleanup_and_exit():
                    print(f"[INFO] 프로그램 종료 전 정리 작업 수행 중...")
                    # 여기에 필요한 정리 작업 코드 추가 가능

                # 정리 함수 등록 (이미 등록되어 있다면 다시 등록할 필요 없음)
                import atexit
                atexit.register(cleanup_and_exit)

                # 프로그램 종료 - 자동으로 등록된 모든 atexit 핸들러가 호출됨
                import sys
                sys.exit(0)
        else:
            # 카카오 API 경로 데이터가 없는 경우 오류 메시지 출력
            print(f"[WARNING] 카카오 API 경로 데이터가 없습니다. 위치 업데이트를 건너뜁니다 - MDN: {self.mdn}")
            # 위치는 변경하지 않음
            print(f"[DEBUG] 위치 유지: ({self.last_latitude}, {self.last_longitude}) - MDN: {self.mdn}")

        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.active_emulators = {self.mdn: self.get_emulator_dict()}
        print(f"[DEBUG] active_emulators 업데이트 완료 - MDN: {self.mdn}")

        # 마지막 위치 정보 업데이트
        self.last_positions[self.mdn] = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }
        print(f"[DEBUG] 마지막 위치 정보 업데이트 완료 - MDN: {self.mdn}, 좌표: ({self.last_latitude}, {self.last_longitude})")

    def _data_collection_worker(self, interval_sec: float, batch_size: int, send_interval_sec: float, stop_event: threading.Event):
        """
        실시간 데이터 생성 스레드 작업

        Args:
            interval_sec: 데이터 생성 간격 (초)
            batch_size: 데이터 수집 배치 크기
            send_interval_sec: 데이터 전송 주기 (초)
            stop_event: 중지 신호를 받기 위한 이벤트
        """
        count = 0
        prev_lat = self.last_latitude
        prev_lon = self.last_longitude
        prev_time = datetime.now()
        prev_speed = 0.0
        prev_angle = 0.0
        last_send_time = datetime.now()

        while not stop_event.is_set():
            # 에뮬레이터가 활성화 상태인 경우만 데이터 생성
            if self.is_active:
                # 현재 시간
                current_time = datetime.now()

                # 실시간 데이터 생성 - 위치 업데이트
                self.update_position()

                # 이동 거리 계산 (미터)
                from services.log_generators.base_log_generator import BaseLogGenerator
                distance = BaseLogGenerator.calculate_distance(None, prev_lat, prev_lon, self.last_latitude, self.last_longitude)

                # 시간 간격 계산 (초)
                time_diff = (current_time - prev_time).total_seconds()
                if time_diff <= 0:
                    time_diff = interval_sec  # 시간 차이가 없거나 음수인 경우 interval_sec 사용

                # 속도 계산 (km/h) - 거리(m) / 시간(초) * 3.6
                if distance > 0 and time_diff > 0:
                    current_speed = (distance / time_diff) * 3.6
                    # 급격한 속도 변화 방지를 위한 스무딩 (이전 속도의 70%, 현재 속도의 30%)
                    speed = prev_speed * 0.7 + current_speed * 0.3
                else:
                    speed = prev_speed * 0.9  # 이동이 없으면 감속

                # 속도 제한 (0~120 km/h)
                speed = max(0, min(120, speed))

                # 방향각 계산 (두 좌표 사이의 방위각)
                if distance > 0:
                    import math
                    # 위도/경도를 라디안으로 변환
                    lat1_rad = math.radians(prev_lat)
                    lon1_rad = math.radians(prev_lon)
                    lat2_rad = math.radians(self.last_latitude)
                    lon2_rad = math.radians(self.last_longitude)

                    # 방위각 계산 (북쪽이 0도, 시계 방향)
                    y = math.sin(lon2_rad - lon1_rad) * math.cos(lat2_rad)
                    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon2_rad - lon1_rad)
                    angle_rad = math.atan2(y, x)
                    angle = (math.degrees(angle_rad) + 360) % 360

                    # 급격한 방향 변화 방지를 위한 스무딩 (이전 방향의 80%, 현재 방향의 20%)
                    # 단, 방향 차이가 180도 이상이면 스무딩 없이 새 방향 사용
                    angle_diff = abs(angle - prev_angle)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff

                    if angle_diff < 180:
                        angle = prev_angle * 0.8 + angle * 0.2
                else:
                    angle = prev_angle  # 이동이 없으면 이전 방향 유지

                # 생성된 데이터 저장
                data_point = {
                    "timestamp": current_time,
                    "latitude": self.last_latitude,
                    "longitude": self.last_longitude,
                    "speed": speed,  # 계산된 속도 (km/h)
                    "angle": angle,  # 계산된 방향각
                    "battery": random.uniform(70, 100),  # 배터리 레벨
                }

                self.collecting_data.append(data_point)
                count += 1

                # 이전 값 업데이트
                prev_lat = self.last_latitude
                prev_lon = self.last_longitude
                prev_time = current_time
                prev_speed = speed
                prev_angle = angle

                # 전송 주기에 도달하거나 배치 크기에 도달하면 콜백 함수 호출
                time_since_last_send = (current_time - last_send_time).total_seconds()
                if ((time_since_last_send >= send_interval_sec) or (count >= batch_size)) and self.data_callback and callable(self.data_callback):
                    # 마지막 데이터 포인트 저장
                    if self.collecting_data:
                        self.last_gps_batch_data = self.collecting_data[-1]
                        print(f"[DEBUG] 마지막 GPS 주기정보 데이터 저장 - MDN: {self.mdn}, 좌표: ({self.last_gps_batch_data['latitude']}, {self.last_gps_batch_data['longitude']})")

                    self.data_callback(self.mdn, self.collecting_data)
                    self.collecting_data = []
                    count = 0
                    last_send_time = current_time

            # 다음 생성 시기까지 대기
            time.sleep(interval_sec)

    def get_emulator_data(self) -> Optional[VehicleData]:
        """
        에뮬레이터의 현재 데이터 가져오기
        """
        if not self.is_active:
            return None

        if self.is_active:
            # 카카오 API 경로 데이터를 사용하여 위치 업데이트
            self.update_position()

            # 마지막 위치 정보는 update_position 메서드에서 업데이트됨

        return VehicleData(
            mdn=self.mdn,
            terminal_id=self.terminal_id,
            manufacture_id=self.manufacture_id,
            packet_version=self.packet_version,
            device_id=self.device_id,
            device_firmware_version=self.device_firmware_version,
            latitude=self.last_latitude,
            longitude=self.last_longitude,
            speed=random.uniform(0, 80) if self.is_active else 0,
            heading=random.randint(0, 359) if self.is_active else 0,
            battery_level=random.uniform(50, 100),
            engine_temperature=random.uniform(70, 95) if self.is_active else random.uniform(20, 30),
            timestamp=datetime.now()
        )

    def get_emulator_dict(self) -> Dict[str, Any]:
        """
        에뮬레이터 정보를 딕셔너리로 반환 (이전 버전과의 호환성을 위함)

        Returns:
            Dict[str, Any]: 에뮬레이터 정보 딕셔너리
        """
        return {
            "mdn": self.mdn,
            "terminal_id": self.terminal_id,
            "manufacture_id": self.manufacture_id,
            "packet_version": self.packet_version,
            "device_id": self.device_id,
            "device_firmware_version": self.device_firmware_version,
            "last_latitude": self.last_latitude,
            "last_longitude": self.last_longitude,
            "is_active": self.is_active,
            "last_update": self.last_update,
            "accumulated_distance": self.accumulated_distance,
            "last_power_on_time": getattr(self, "last_power_on_time", "")
        }

    def is_emulator_exists(self, mdn: str = None) -> bool:
        """
        에뮬레이터가 존재하는지 확인

        Args:
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)
        """
        # 단일 에뮬레이터이므로 항상 존재함
        # 단, 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn is not None and mdn != self.mdn:
            return False
        return True

    def is_emulator_active(self, mdn: str = None) -> bool:
        """
        에뮬레이터가 활성 상태인지 확인

        Args:
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)
        """
        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn is not None and mdn != self.mdn:
            return False
        return self.is_active

    def update_vehicle_power_state(self, power_on: bool) -> Tuple[bool, str]:
        """
        백엔드에 차량 전원 상태 업데이트 (비활성화됨)

        Args:
            power_on: 전원 상태 (True: ON, False: OFF)

        Returns:
            (성공 여부, 오류 메시지)
        """
        # 더 이상 백엔드 API 직접 호출 없이 로그만 남김 (제거된 기능)

        # 로그만 출력    
        print(f"[INFO] 차량 전원 상태 업데이트 로그: MDN={self.mdn}, powerOn={power_on} (API 호출 없음)")
        return True, "전원 상태 업데이트 성공 (로그만 기록)"

    def update_emulator_position(self, latitude: float, longitude: float, distance: float = 0) -> bool:
        """
        에뮬레이터 위치 업데이트

        Args:
            latitude: 위도
            longitude: 경도
            distance: 이동 거리 (미터)
        """
        self.last_latitude = latitude
        self.last_longitude = longitude
        self.last_update = datetime.now()

        # 누적 주행거리 업데이트
        if distance > 0:
            self.accumulated_distance += distance
            # MDN별 누적 거리 딕셔너리 업데이트
            self.mdn_accumulated_distances[self.mdn] = self.accumulated_distance

        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.active_emulators = {self.mdn: self.get_emulator_dict()}

        # 마지막 위치 정보 업데이트
        self.last_positions[self.mdn] = {
            "latitude": self.last_latitude,
            "longitude": self.last_longitude,
            "timestamp": datetime.now()
        }

        return True

    def get_accumulated_distance(self, mdn: str = None) -> int:
        """
        누적 주행거리 조회 (미터)

        Args:
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)
        """
        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn is not None and mdn != self.mdn:
            return 0

        return self.accumulated_distance

    def update_accumulated_distance(self, distance: int, mdn: str = None) -> bool:
        """
        누적 주행거리 업데이트 (미터)

        Args:
            distance: 누적 주행거리 (미터)
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)

        Returns:
            bool: 성공 여부
        """
        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn is not None and mdn != self.mdn:
            return False

        self.accumulated_distance = distance
        # MDN별 누적 거리 딕셔너리 업데이트
        self.mdn_accumulated_distances[self.mdn] = distance

        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.active_emulators = {self.mdn: self.get_emulator_dict()}

        return True

    def update_location(self, latitude: float, longitude: float, mdn: str = None) -> bool:
        """
        단말기 위치 정보 업데이트

        Args:
            latitude: 위도
            longitude: 경도
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)

        Returns:
            bool: 성공 여부
        """
        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn is not None and mdn != self.mdn:
            return False

        return self.update_emulator_position(latitude, longitude)

    def get_last_position(self, mdn: str = None) -> dict:
        """
        마지막 위치 정보 가져오기 (시동 OFF 시 저장한 위치)

        Args:
            mdn: 차량 번호 (단말기 번호), 기본값은 None (무시됨)

        Returns:
            dict: 마지막 위치 정보 또는 None
        """
        # 요청된 MDN이 현재 에뮬레이터의 MDN과 일치하는지 확인
        if mdn is not None and mdn != self.mdn:
            return None

        # 위치 데이터에 좌표가 있는 경우 문자열로 변환
        heading = str(random.randint(0, 359))
        accumulated_distance = str(self.accumulated_distance)

        return {
            "latitude": str(int(self.last_position["latitude"] * 1000000)),  # Java 백엔드 형식에 맞춰서 1,000,000 곱하기
            "longitude": str(int(self.last_position["longitude"] * 1000000)),
            "heading": heading,
            "accumulated_distance": accumulated_distance
        }

    def set_kakao_route_data(self, route_points: List[Dict]) -> bool:
        """
        카카오 API 경로 데이터 설정

        Args:
            route_points: 경로 포인트 목록 [{"latitude": float, "longitude": float}, ...]

        Returns:
            bool: 성공 여부
        """
        print(f"[DEBUG] 카카오 API 경로 데이터 설정 시작 - MDN: {self.mdn}, 포인트 수: {len(route_points) if route_points else 0}")

        if not route_points:
            print(f"[ERROR] 경로 포인트가 없습니다 - MDN: {self.mdn}")
            return False

        # 경로 데이터 유효성 검사
        valid_points = True
        for i, point in enumerate(route_points[:5]):  # 처음 5개 포인트만 로깅
            if "latitude" not in point or "longitude" not in point:
                print(f"[ERROR] 유효하지 않은 경로 포인트 형식 - 인덱스: {i}, 포인트: {point}")
                valid_points = False
                break

        if not valid_points:
            print(f"[ERROR] 유효하지 않은 경로 포인트가 포함되어 있습니다 - MDN: {self.mdn}")
            return False

        # 경로 데이터 설정
        print(f"[DEBUG] 경로 데이터 설정 중 - 이전 포인트 수: {len(self.kakao_route_points) if self.kakao_route_points else 0}, 새 포인트 수: {len(route_points)}")
        self.kakao_route_points = route_points
        self.current_route_index = 0
        print(f"[DEBUG] 경로 데이터 설정 완료 - 현재 인덱스: {self.current_route_index}")

        # 첫 번째 포인트로 위치 초기화
        if len(route_points) > 0:
            first_point = route_points[0]
            print(f"[DEBUG] 첫 번째 포인트로 위치 초기화 - 좌표: ({first_point['latitude']}, {first_point['longitude']})")

            # 이전 위치 저장 (디버깅용)
            prev_lat = self.last_latitude
            prev_lon = self.last_longitude

            # 새 위치 설정
            self.last_latitude = first_point["latitude"]
            self.last_longitude = first_point["longitude"]

            print(f"[DEBUG] 위치 업데이트 - 이전: ({prev_lat}, {prev_lon}), 새 위치: ({self.last_latitude}, {self.last_longitude})")

            # 마지막 위치 정보 업데이트
            self.last_positions[self.mdn] = {
                "latitude": self.last_latitude,
                "longitude": self.last_longitude,
                "timestamp": datetime.now()
            }
            print(f"[DEBUG] 마지막 위치 정보 업데이트 완료 - MDN: {self.mdn}")

        print(f"[INFO] 카카오 API 경로 데이터 설정 완료: {len(route_points)}개 포인트 - MDN: {self.mdn}")
        return True
