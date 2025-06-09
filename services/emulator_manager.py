import random
import time
import threading
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple
from models.emulator_data import VehicleData

class EmulatorManager:
    """
    에뮬레이터 상태 관리 클래스
    - 에뮬레이터 시작/중지 관리
    - 에뮬레이터 상태 정보 관리
    - 위치, 승객, 시간 등의 데이터 관리
    """
    
    def __init__(self):
        # 활성화된 에뮬레이터 정보 저장
        self.active_emulators = {}
        # 마지막 위치 캐시 (시동 OFF 시 마지막 위치 저장)
        self.last_positions = {}  # mdn -> position_data
        # 실시간 데이터 수집을 위한 타이머 스레드 관리
        self.data_timers = {}  # mdn -> timer_thread
        self.collecting_data = {}  # mdn -> [gps_data_points]
        self.data_callbacks = {}  # mdn -> callback_function
        # 백엔드 API 설정
        self.backend_url = "http://localhost:8080/api/vehicles"
    
    def start_emulator(self, mdn: str, terminal_id: str = "A001", manufacture_id: int = 6, 
                        packet_version: int = 5, device_id: int = 1, device_firmware_version: str = "1.0.0") -> bool:
        """
        에뮬레이터 데이터 생성 시작
        
        Args:
            mdn: 차량 번호 (단말기 번호)
            terminal_id: 터미널 아이디 (차량관제는 'A001'로 고정)
            manufacture_id: 제조사 아이디 (CNSLink는 '6' 값 사용)
            packet_version: 패킷 버전 (M2M 버전이 5이므로 '5'로 고정)
            device_id: 디바이스 아이디 (GPS로만 운영함으로 '1'로 고정)
            device_firmware_version: 디바이스 펌웨어 버전
        """
        # 초기 위치 - 서울시 중심부 근처
        initial_latitude = 37.5665 + random.uniform(-0.01, 0.01)
        initial_longitude = 126.9780 + random.uniform(-0.01, 0.01)
        
        # 에뮬레이터 데이터 생성
        self.active_emulators[mdn] = {
            "terminal_id": terminal_id,  # 고정: 'A001'
            "manufacture_id": manufacture_id,  # 고정: 6
            "packet_version": packet_version,  # 고정: 5
            "device_id": device_id,  # 고정: 1
            "device_firmware_version": device_firmware_version,
            "last_latitude": initial_latitude,
            "last_longitude": initial_longitude,
            "is_active": True,
            "last_update": datetime.now(),
            "accumulated_distance": 0,  # 누적 주행거리 (미터)
            "vehicle_id": int(mdn)  # mdn을 차량 ID로 사용
        }
        
        # 마지막 위치 저장
        self.last_positions[mdn] = {
            "latitude": initial_latitude,
            "longitude": initial_longitude,
            "timestamp": datetime.now()
        }
        
        # 백엔드에 전원 상태 업데이트 (powerOn = True)
        self.update_vehicle_power_state(mdn, True)
        
        return True
    
    def stop_emulator(self, mdn: str) -> bool:
        """
        에뮬레이터 데이터 생성 중지
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn in self.active_emulators:
            # 마지막 위치 저장 (시동 OFF 시 사용)
            self.last_positions[mdn] = {
                "latitude": self.active_emulators[mdn]["last_latitude"],
                "longitude": self.active_emulators[mdn]["last_longitude"],
                "timestamp": datetime.now()
            }
            
            # 에뮬레이터 비활성화 처리
            self.active_emulators[mdn]["is_active"] = False
            
            # 실시간 데이터 생성 타이머 중지
            self.stop_realtime_data_collection(mdn)
            
            # 백엔드에 전원 상태 업데이트 (powerOn = False)
            self.update_vehicle_power_state(mdn, False)
            
            return True
        
        # 해당 MDN의 에뮬레이터가 존재하지 않음
        return False
        
    def start_realtime_data_collection(self, mdn: str, callback: Callable[[str, list], None], interval_sec: float = 1.0, batch_size: int = 60):
        """
        실시간 GPS 데이터 생성 시작
        
        Args:
            mdn: 차량 번호 (단말기 번호)
            callback: 배치가 채워졌을 때 호출될 함수 (mdn, data_list)
            interval_sec: 데이터 생성 간격 (초)
            batch_size: 데이터 수집 배치 크기
        """
        # 기존 타이머가 있다면 먼저 중지
        self.stop_realtime_data_collection(mdn)
        
        # 새로운 데이터 수집 시작
        if mdn in self.active_emulators and self.active_emulators[mdn]["is_active"]:
            self.collecting_data[mdn] = []
            self.data_callbacks[mdn] = callback
            
            # 타이머 스레드 생성
            stop_event = threading.Event()
            timer_thread = threading.Thread(
                target=self._data_collection_worker,
                args=(mdn, interval_sec, batch_size, stop_event),
                daemon=True
            )
            
            self.data_timers[mdn] = {
                "thread": timer_thread,
                "stop_event": stop_event
            }
            
            timer_thread.start()
            print(f"Started real-time data collection for MDN: {mdn}")
            return True
        return False
    
    def stop_realtime_data_collection(self, mdn: str) -> bool:
        """
        실시간 데이터 수집 중지
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn in self.data_timers:
            self.data_timers[mdn]["stop_event"].set()
            self.data_timers[mdn]["thread"].join(timeout=2.0)
            del self.data_timers[mdn]
            
            # 남은 데이터 처리
            if mdn in self.collecting_data and self.collecting_data[mdn]:
                if mdn in self.data_callbacks and callable(self.data_callbacks[mdn]):
                    self.data_callbacks[mdn](mdn, self.collecting_data[mdn])
                self.collecting_data[mdn] = []
                
            return True
        return False
    
    def update_position(self, mdn: str):
        """
        에뮬레이터 위치 랜덤 업데이트
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn in self.active_emulators and self.active_emulators[mdn]["is_active"]:
            # 현재 좌표값 확인
            current_lat = self.active_emulators[mdn]["last_latitude"]
            current_lon = self.active_emulators[mdn]["last_longitude"]
            
            # 좌표가 비정상적으로 작은 경우 (서울 좌표로 초기화)
            if abs(current_lat) < 1.0:  # 위도가 1도보다 작으면 비정상으로 판단
                self.active_emulators[mdn]["last_latitude"] = 37.5665
                self.active_emulators[mdn]["last_longitude"] = 126.9780
                print(f"위치 초기화: {mdn} - 서울 좌표로 재설정 (37.5665, 126.9780)")
            
            # 위치 랜덤 업데이트 (더 큰 변화를 주도록 값 증가)
            self.active_emulators[mdn]["last_latitude"] += random.uniform(-0.001, 0.001)
            self.active_emulators[mdn]["last_longitude"] += random.uniform(-0.001, 0.001)
    
    def _data_collection_worker(self, mdn: str, interval_sec: float, batch_size: int, stop_event: threading.Event):
        """
        실시간 데이터 생성 스레드 작업
        
        Args:
            mdn: 차량 번호
            interval_sec: 데이터 생성 간격 (초)
            batch_size: 데이터 수집 배치 크기
            stop_event: 중지 신호를 받기 위한 이벤트
        """
        count = 0
        
        while not stop_event.is_set() and mdn in self.active_emulators:
            # 에뮬레이터가 활성화 상탌인 경우만 데이터 생성
            if self.active_emulators[mdn]["is_active"]:
                # 실시간 데이터 생성 - 위치 업데이트
                self.update_position(mdn)
                
                # 생성된 데이터 저장
                data_point = {
                    "timestamp": datetime.now(),
                    "latitude": self.active_emulators[mdn]["last_latitude"],
                    "longitude": self.active_emulators[mdn]["last_longitude"],
                    "speed": random.uniform(0, 60),  # km/h
                    "angle": random.uniform(0, 360),  # 방향각
                    "battery": random.uniform(70, 100),  # 배터리 레벨
                }
                
                self.collecting_data[mdn].append(data_point)
                count += 1
                
                # 배치 크기에 도달하면 콜백 함수 호출
                if count >= batch_size and mdn in self.data_callbacks and callable(self.data_callbacks[mdn]):
                    self.data_callbacks[mdn](mdn, self.collecting_data[mdn])
                    self.collecting_data[mdn] = []
                    count = 0
            
            # 다음 생성 시기까지 대기
            time.sleep(interval_sec)
    
    def get_emulator_data(self, mdn: str) -> Optional[VehicleData]:
        """
        에뮬레이터의 현재 데이터 가져오기
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn not in self.active_emulators or not self.active_emulators[mdn]["is_active"]:
            return None
        
        emulator = self.active_emulators[mdn]
        
        if emulator["is_active"]:
            # 위치 약간 변경 (실시간 업데이트 시뮬레이션)
            emulator["last_latitude"] += random.uniform(-0.0001, 0.0001)
            emulator["last_longitude"] += random.uniform(-0.0001, 0.0001)
        
        return VehicleData(
            mdn=mdn,
            terminal_id=emulator["terminal_id"],
            manufacture_id=emulator["manufacture_id"],
            packet_version=emulator["packet_version"],
            device_id=emulator["device_id"],
            device_firmware_version=emulator["device_firmware_version"],
            latitude=emulator["last_latitude"],
            longitude=emulator["last_longitude"],
            speed=random.uniform(0, 80) if emulator["is_active"] else 0,
            heading=random.randint(0, 359) if emulator["is_active"] else 0,
            battery_level=random.uniform(50, 100),
            engine_temperature=random.uniform(70, 95) if emulator["is_active"] else random.uniform(20, 30),
            timestamp=datetime.now()
        )
    
    def is_emulator_exists(self, mdn: str) -> bool:
        """
        에뮬레이터가 존재하는지 확인
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        return mdn in self.active_emulators
    
    def is_emulator_active(self, mdn: str) -> bool:
        """
        에뮬레이터가 활성 상태인지 확인
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        return mdn in self.active_emulators and self.active_emulators[mdn]["is_active"]
        
    def update_vehicle_power_state(self, mdn: str, power_on: bool) -> Tuple[bool, str]:
        """
        백엔드에 차량 전원 상태 업데이트
        
        Args:
            mdn: 차량 번호 (단말기 번호)
            power_on: 전원 상태 (True: ON, False: OFF)
            
        Returns:
            (성공 여부, 오류 메시지)
        """
        if mdn not in self.active_emulators:
            return False, f"MDN {mdn}에 대한 차량 정보가 없습니다."
            
        vehicle_id = self.active_emulators[mdn].get("vehicle_id", int(mdn))
        endpoint = f"{self.backend_url}/{vehicle_id}/power"
        
        try:
            print(f"[백엔드 통신] 차량 전원 상태 업데이트: ID={vehicle_id}, powerOn={power_on}")
            response = requests.patch(
                endpoint,
                params={"powerOn": power_on},
                timeout=5
            )
            
            if response.status_code == 200:
                print(f"[백엔드 통신] 전원 상태 업데이트 성공: {vehicle_id}, powerOn={power_on}")
                return True, "전원 상태 업데이트 성공"
            else:
                error_msg = f"[오류] 전원 상태 업데이트 실패: HTTP {response.status_code} - {response.text}"
                print(error_msg)
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            error_msg = f"[오류] 백엔드 서버 연결 실패 (전원 상태 업데이트): {str(e)}"
            print(error_msg)
            return False, error_msg
    
    def update_emulator_position(self, mdn: str, latitude: float, longitude: float, distance: float = 0) -> bool:
        """
        에뮬레이터 위치 업데이트
        
        Args:
            mdn: 차량 번호 (단말기 번호)
            latitude: 위도
            longitude: 경도
            distance: 이동 거리 (미터)
        """
        if mdn not in self.active_emulators:
            return False
            
        self.active_emulators[mdn]["last_latitude"] = latitude
        self.active_emulators[mdn]["last_longitude"] = longitude
        self.active_emulators[mdn]["last_update"] = datetime.now()
        
        # 누적 주행거리 업데이트
        if distance > 0:
            self.active_emulators[mdn]["accumulated_distance"] += distance
            
        return True
    
    def get_accumulated_distance(self, mdn: str) -> int:
        """
        누적 주행거리 조회 (미터)
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn not in self.active_emulators:
            return 0
            
        return self.active_emulators[mdn]["accumulated_distance"]
