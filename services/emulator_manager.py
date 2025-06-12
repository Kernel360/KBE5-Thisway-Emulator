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

    def start_realtime_data_collection(self, mdn: str = None, callback: Callable[[str, list], None] = None, interval_sec: float = 1.0, batch_size: int = 60):
        """
        실시간 GPS 데이터 생성 시작

        Args:
            mdn: 차량 번호(MDN), 기본값은 None (현재 에뮬레이터의 MDN 사용)
            callback: 배치가 채워졌을 때 호출될 함수 (mdn, data_list)
            interval_sec: 데이터 생성 간격 (초)
            batch_size: 데이터 수집 배치 크기
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
                args=(interval_sec, batch_size, self.stop_event),
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
            self.data_timer.join(timeout=2.0)
            self.data_timer = None

            # 남은 데이터 처리
            if self.collecting_data and self.data_callback and callable(self.data_callback):
                self.data_callback(self.mdn, self.collecting_data)
                self.collecting_data = []

            return True
        return False

    def update_position(self):
        """
        에뮬레이터 위치 랜덤 업데이트
        """
        if self.is_active:
            # 현재 좌표값 확인
            # 좌표가 비정상적으로 작은 경우 (서울 좌표로 초기화)
            if abs(self.last_latitude) < 1.0:  # 위도가 1도보다 작으면 비정상으로 판단
                self.last_latitude = 37.5665
                self.last_longitude = 126.9780
                print(f"위치 초기화: {self.mdn} - 서울 좌표로 재설정 (37.5665, 126.9780)")

            # 위치 랜덤 업데이트 (더 큰 변화를 주도록 값 증가)
            self.last_latitude += random.uniform(-0.001, 0.001)
            self.last_longitude += random.uniform(-0.001, 0.001)

            # 이전 버전과의 호환성을 위한 active_emulators 업데이트
            self.active_emulators = {self.mdn: self.get_emulator_dict()}

            # 마지막 위치 정보 업데이트
            self.last_positions[self.mdn] = {
                "latitude": self.last_latitude,
                "longitude": self.last_longitude,
                "timestamp": datetime.now()
            }

    def _data_collection_worker(self, interval_sec: float, batch_size: int, stop_event: threading.Event):
        """
        실시간 데이터 생성 스레드 작업

        Args:
            interval_sec: 데이터 생성 간격 (초)
            batch_size: 데이터 수집 배치 크기
            stop_event: 중지 신호를 받기 위한 이벤트
        """
        count = 0
        prev_lat = self.last_latitude
        prev_lon = self.last_longitude
        prev_time = datetime.now()
        prev_speed = 0.0
        prev_angle = 0.0

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

                # 배치 크기에 도달하면 콜백 함수 호출
                if count >= batch_size and self.data_callback and callable(self.data_callback):
                    self.data_callback(self.mdn, self.collecting_data)
                    self.collecting_data = []
                    count = 0

            # 다음 생성 시기까지 대기
            time.sleep(interval_sec)

    def get_emulator_data(self) -> Optional[VehicleData]:
        """
        에뮬레이터의 현재 데이터 가져오기
        """
        if not self.is_active:
            return None

        if self.is_active:
            # 위치 약간 변경 (실시간 업데이트 시뮬레이션)
            self.last_latitude += random.uniform(-0.0001, 0.0001)
            self.last_longitude += random.uniform(-0.0001, 0.0001)

            # 마지막 위치 정보 업데이트
            self.last_positions[self.mdn] = {
                "latitude": self.last_latitude,
                "longitude": self.last_longitude,
                "timestamp": datetime.now()
            }

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
