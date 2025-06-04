import random
import time
from datetime import datetime
from models.emulator_data import VehicleData

class EmulatorDataGenerator:
    def __init__(self):
        self.active_emulators = {}  # mdn -> emulator_data
    
    def start_emulator(self, mdn: str, terminal_id: str, manufacture_id: int, 
                      packet_version: int, device_id: int, device_firmware_version: str):
        """에뮬레이터 데이터 생성 시작"""
        self.active_emulators[mdn] = {
            "terminal_id": terminal_id,
            "manufacture_id": manufacture_id,
            "packet_version": packet_version,
            "device_id": device_id,
            "device_firmware_version": device_firmware_version,
            "last_latitude": random.uniform(35.0, 38.0),  # 한국 위도 범위
            "last_longitude": random.uniform(125.0, 129.0),  # 한국 경도 범위
            "last_update": datetime.now(),
            "is_active": True
        }
        return True
    
    def stop_emulator(self, mdn: str):
        """에뮬레이터 데이터 생성 중지"""
        if mdn in self.active_emulators:
            self.active_emulators[mdn]["is_active"] = False
            return True
        return False
    
    def get_emulator_data(self, mdn: str) -> VehicleData:
        """에뮬레이터의 현재 데이터 가져오기"""
        if mdn not in self.active_emulators or not self.active_emulators[mdn]["is_active"]:
            return None
        
        emulator = self.active_emulators[mdn]
        
        # 활성 상태인 경우 위치 약간 업데이트
        if emulator["is_active"]:
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

# 싱글톤 인스턴스
data_generator = EmulatorDataGenerator()
