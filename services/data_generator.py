import random
import time
import math
import threading
import queue
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any, Optional, Tuple
from models.emulator_data import VehicleData, GpsLogRequest, GpsLogItem
from services.emulator_manager import EmulatorManager
from services.gps_log_generator import GpsLogGenerator
from services.log_storage_manager import LogStorageManager

class EmulatorDataGenerator:
    """
    기존 에뮬레이터 데이터 생성 클래스를 분리된 서비스 모듈에 위임하는 파사드 클래스.
    하위 호환성을 위해 기존 메소드들을 유지하고 적절한 서비스 클래스에 위임합니다.
    """
    
    def __init__(self):
        # 분리된 서비스 클래스 인스턴스 생성
        self.emulator_manager = EmulatorManager()
        self.log_storage_manager = LogStorageManager(max_storage_hours=1, send_interval_seconds=30)
        self.gps_log_generator = GpsLogGenerator(self.emulator_manager)
        
        # 로그 전송 스레드 시작
        self.log_storage_manager.start_sender_thread()
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        두 지점 간의 거리를 미터 단위로 계산 (Haversine 공식)
        """
        # GpsLogGenerator에 위임
        return self.gps_log_generator.calculate_distance(lat1, lon1, lat2, lon2)
    
    def generate_gps_log(self, mdn: str, generate_full: bool = True) -> GpsLogRequest:
        """
        GPS 로그 요청 데이터 생성 (0~59초 데이터)
        generate_full: True면 60개의 전체 데이터 생성, False면 스냅샷용 1개만 생성
        """
        # GpsLogGenerator에 위임
        return self.gps_log_generator.generate_gps_log(mdn, generate_full)
        
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
            
        Returns:
            bool: 성공 여부
        """
        # EmulatorManager에 위임
        success = self.emulator_manager.start_emulator(
            mdn, terminal_id, manufacture_id, packet_version, device_id, device_firmware_version
        )
        
        if success:
            # 실시간 데이터 생성 및 수집 시작 (1초마다 데이터 생성, 60초마다 배치 처리)
            self.emulator_manager.start_realtime_data_collection(
                mdn=mdn,
                callback=self._process_collected_data,
                interval_sec=1.0,
                batch_size=60
            )
            print(f"Started real-time data collection for MDN: {mdn} - Will send batch every 60 seconds")
        
        return success
        
    def _process_collected_data(self, mdn: str, collected_data: list):
        """
        수집된 GPS 데이터를 처리하고 백엔드로 전송
        
        Args:
            mdn: 차량 번호 (단말기 번호)
            collected_data: 60초 동안 수집된 실시간 데이터
        """
        if not collected_data:
            return
            
        print(f"Processing batch of {len(collected_data)} data points for MDN: {mdn}")
        
        # 수집된 데이터로 GPS 로그 생성
        gps_log = self.gps_log_generator.create_gps_log_from_collected_data(mdn, collected_data)
        
        if gps_log:
            # 백엔드로 전송할 로그 저장
            self.log_storage_manager.store_unsent_log(mdn, gps_log)
            print(f"Stored GPS log with {len(gps_log.cList)} items for MDN: {mdn}")
        else:
            print(f"Failed to create GPS log from collected data for MDN: {mdn}")
    
    def stop_emulator(self, mdn: str) -> bool:
        """에뮬레이터 데이터 생성 중지"""
        # EmulatorManager에 위임
        return self.emulator_manager.stop_emulator(mdn)
    
    def get_emulator_data(self, mdn: str) -> VehicleData:
        """에뮬레이터의 현재 데이터 가져오기"""
        # EmulatorManager에 위임
        return self.emulator_manager.get_emulator_data(mdn)

    def generate_gps_log_sample(self, mdn: str) -> GpsLogRequest:
        """간소화된 GPS 로그 요청 샘플 데이터 생성 (하위 호환용)"""
        # GpsLogGenerator에 위임
        return self.gps_log_generator.generate_gps_log(mdn, generate_full=False)
    
    def store_unsent_log(self, mdn: str, log_data: GpsLogRequest) -> bool:
        """미전송 로그 데이터 저장 (최대 1시간)"""
        # LogStorageManager에 위임
        return self.log_storage_manager.store_unsent_log(mdn, log_data)
    
    def get_unsent_logs(self, mdn: str) -> List[GpsLogRequest]:
        """미전송 로그 데이터 가져오기 (최대 1시간)"""
        # LogStorageManager에 위임
        return self.log_storage_manager.get_unsent_logs(mdn)
    
    def clear_unsent_logs(self, mdn: str) -> bool:
        """미전송 로그 데이터 삭제"""
        # LogStorageManager에 위임
        return self.log_storage_manager.clear_unsent_logs(mdn)
    
    def has_pending_logs(self, mdn: str) -> bool:
        """미전송 로그가 있는지 확인"""
        # LogStorageManager에 위임
        return self.log_storage_manager.has_pending_logs(mdn)
    
    def count_pending_logs(self, mdn: str) -> int:
        """미전송 로그 개수 확인"""
        # LogStorageManager에 위임
        return self.log_storage_manager.count_pending_logs(mdn)
    
    def process_received_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        받은 GPS 로그 처리 및 에뮬레이터 상태 업데이트
        """
        # GpsLogGenerator에 위임
        return self.gps_log_generator.process_received_gps_log(log_data)
    
    def process_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        받은 GPS 로그 전체 처리
        1. 에뮬레이터 상태 업데이트
        2. 전송 완료 확인 (= 로그 처리 완료)
        """
        # GpsLogGenerator에 위임
        return self.gps_log_generator.process_received_gps_log(log_data)

# 싱글톤 인스턴스
data_generator = EmulatorDataGenerator()
