"""
데이터 생성기 파사드 클래스
로그 타입별 생성기 클래스를 통합 관리하는 파사드 패턴 구현
"""

import threading
import queue
from typing import List, Dict, Any, Optional

from models.emulator_data import VehicleData, GpsLogRequest, PowerLogRequest, GeofenceLogRequest
from services.emulator_manager import EmulatorManager
from services.log_storage_manager import LogStorageManager
from services.log_generators.gps_log_generator import GpsLogGenerator
from services.log_generators.power_log_generator import PowerLogGenerator
from services.log_generators.geofence_log_generator import GeofenceLogGenerator

class EmulatorDataGenerator:
    """
    에뮬레이터 데이터 생성 파사드 클래스
    각 로그 타입별 생성기를 관리하고 필요한 작업을 위임합니다.
    """

    def __init__(self):
        """에뮬레이터 데이터 생성기 초기화"""
        # 에뮬레이터 관리자
        self.emulator_manager = EmulatorManager()

        # 로그 저장 관리자
        self.log_storage_manager = LogStorageManager()

        # 타입별 로그 생성기 초기화
        self.gps_generator = GpsLogGenerator(self.emulator_manager)
        self.power_generator = PowerLogGenerator(self.emulator_manager)
        self.geofence_generator = GeofenceLogGenerator(self.emulator_manager)

        # 데이터 생성 상태
        self.is_generating = {}
        self.generate_threads = {}
        self.stop_events = {}

        print("[INFO] 에뮬레이터 데이터 생성기 초기화 완료")

    #
    # GPS 로그 관련 메서드
    #

    def generate_gps_log(self, mdn: str, generate_full: bool = True) -> Optional[GpsLogRequest]:
        """
        GPS 로그 생성 (GpsLogGenerator에 위임)

        Args:
            mdn: 차량 번호(MDN)
            generate_full: True면 전체 데이터 생성, False면 스냅샷용 데이터만 생성

        Returns:
            Optional[GpsLogRequest]: 생성된 GPS 로그
        """
        return self.gps_generator.generate_gps_log(mdn, generate_full)

    def store_gps_log(self, mdn: str, log_data: GpsLogRequest) -> bool:
        """
        GPS 로그 저장 (LogStorageManager에 위임)

        Args:
            mdn: 차량 번호(MDN)
            log_data: GPS 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.log_storage_manager.store_gps_log(mdn, log_data)

    def get_vehicle_gps_data(self, mdn: str) -> Dict[str, Any]:
        """
        차량 GPS 데이터 조회

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            Dict[str, Any]: 차량 GPS 데이터
        """
        if not self.emulator_manager.is_emulator_active(mdn):
            return {}

        # 단일 에뮬레이터 모드에서는 직접 속성에서 가져옴
        return {
            "latitude": self.emulator_manager.last_latitude,
            "longitude": self.emulator_manager.last_longitude,
            "is_active": self.emulator_manager.is_active,
            "accumulated_distance": self.emulator_manager.get_accumulated_distance(mdn)
        }

    #
    # 시동 로그 관련 메서드
    #

    def generate_power_log(self, mdn: str, power_on: bool = True) -> Optional[PowerLogRequest]:
        """
        시동 로그 생성 (PowerLogGenerator에 위임)

        Args:
            mdn: 차량 번호(MDN)
            power_on: 시동 ON(True) 또는 OFF(False)

        Returns:
            Optional[PowerLogRequest]: 생성된 시동 로그
        """
        return self.power_generator.generate_power_log(mdn, power_on)

    def store_power_log(self, mdn: str, log_data: PowerLogRequest) -> bool:
        """
        시동 로그 저장 (LogStorageManager에 위임)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 시동 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.log_storage_manager.store_power_log(mdn, log_data)

    #
    # 지오펜스 로그 관련 메서드
    #

    def generate_geofence_log(self, mdn: str, geo_grp_id: str, geo_p_id: str, 
                            evt_val: str = "1") -> Optional[GeofenceLogRequest]:
        """
        지오펜스 로그 생성 (GeofenceLogGenerator에 위임)

        Args:
            mdn: 차량 번호(MDN)
            geo_grp_id: 지오펜스 그룹 ID
            geo_p_id: 지오펜스 포인트 ID
            evt_val: 이벤트 값 (1: 진입, 2: 이탈)

        Returns:
            Optional[GeofenceLogRequest]: 생성된 지오펜스 로그
        """
        return self.geofence_generator.generate_geofence_log(mdn, geo_grp_id, geo_p_id, evt_val)

    def store_geofence_log(self, mdn: str, log_data: GeofenceLogRequest) -> bool:
        """
        지오펜스 로그 저장 (LogStorageManager에 위임)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 지오펜스 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.log_storage_manager.store_geofence_log(mdn, log_data)

    #
    # 로그 처리 메서드
    #

    def process_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        수신된 GPS 로그 데이터 처리

        Args:
            log_data: GPS 로그 요청 데이터

        Returns:
            bool: 처리 성공 여부
        """
        # 에뮬레이터 존재 여부 확인
        if not self.emulator_manager.is_emulator_exists(log_data.mdn):
            print(f"[ERROR] 존재하지 않는 에뮬레이터입니다: {log_data.mdn}")
            return False

        # GPS 로그 저장
        return self.store_gps_log(log_data.mdn, log_data)

    def process_power_log(self, log_data: PowerLogRequest) -> bool:
        """
        수신된 시동 로그 데이터 처리

        Args:
            log_data: 시동 로그 요청 데이터

        Returns:
            bool: 처리 성공 여부
        """
        # 에뮬레이터 존재 여부 확인
        if not self.emulator_manager.is_emulator_exists(log_data.mdn):
            print(f"[ERROR] 존재하지 않는 에뮬레이터입니다: {log_data.mdn}")
            return False

        # 시동 로그 저장
        return self.store_power_log(log_data.mdn, log_data)

    def get_unsent_logs(self, mdn: str) -> list:
        """
        특정 MDN에 대한 미전송 로그 목록 조회

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            list: 미전송 로그 목록
        """
        # 각 핸들러에서 미전송 로그 수집
        gps_logs = self.log_storage_manager.gps_handler.get_pending_logs(mdn)
        power_logs = self.log_storage_manager.power_handler.get_pending_logs(mdn)
        geofence_logs = self.log_storage_manager.geofence_handler.get_pending_logs(mdn)

        # 모든 로그 합치기
        all_logs = gps_logs + power_logs + geofence_logs
        return all_logs

    #
    # 에뮬레이터 제어 메서드
    #

    def start_vehicle(self, mdn: str, send_power_log: bool = True) -> bool:
        """
        차량 시작 (시동 ON)

        Args:
            mdn: 차량 번호(MDN)
            send_power_log: 시동 로그 전송 여부

        Returns:
            bool: 성공 여부
        """
        if not self.emulator_manager.is_emulator_active(mdn):
            return False

        # 차량 활성화 - 단일 에뮬레이터 모드에서는 직접 속성 설정
        self.emulator_manager.is_active = True
        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.emulator_manager.active_emulators = {mdn: self.emulator_manager.get_emulator_dict()}

        # 시동 ON 로그 생성 및 전송
        if send_power_log:
            power_log = self.generate_power_log(mdn, power_on=True)
            if power_log:
                self.store_power_log(mdn, power_log)
                print(f"[INFO] 차량 {mdn} 시동 ON 로그 생성 및 저장 완료")

        return True

    def stop_vehicle(self, mdn: str, send_power_log: bool = True) -> bool:
        """
        차량 정지 (시동 OFF)

        Args:
            mdn: 차량 번호(MDN)
            send_power_log: 시동 로그 전송 여부

        Returns:
            bool: 성공 여부
        """
        print(f"[DEBUG] stop_vehicle 호출됨 - MDN: {mdn}, send_power_log: {send_power_log}")

        if not self.emulator_manager.is_emulator_active(mdn):
            print(f"[WARNING] 에뮬레이터가 활성화되지 않았습니다 - MDN: {mdn}")
            return False

        # 시동 OFF 로그 생성 및 전송 (차량 비활성화 전에 수행)
        if send_power_log:
            print(f"[DEBUG] 시동 OFF 로그 생성 시작 - MDN: {mdn}")
            power_log = self.generate_power_log(mdn, power_on=False)
            if power_log:
                print(f"[DEBUG] 시동 OFF 로그 생성 완료 - MDN: {mdn}, onTime: {power_log.onTime}, offTime: {power_log.offTime}")
                store_result = self.store_power_log(mdn, power_log)
                print(f"[INFO] 차량 {mdn} 시동 OFF 로그 생성 및 저장 {'성공' if store_result else '실패'}")
            else:
                print(f"[ERROR] 시동 OFF 로그 생성 실패 - MDN: {mdn}")

        # 차량 비활성화 - 단일 에뮬레이터 모드에서는 직접 속성 설정
        self.emulator_manager.is_active = False
        # 이전 버전과의 호환성을 위한 active_emulators 업데이트
        self.emulator_manager.active_emulators = {mdn: self.emulator_manager.get_emulator_dict()}
        print(f"[DEBUG] 차량 비활성화 완료 - MDN: {mdn}")

        return True

    def start_emulator(self, mdn: str, terminal_id: str, manufacture_id: int, 
                       packet_version: int, device_id: int, 
                       device_firmware_version: str) -> bool:
        """
        에뮬레이터 시작 (API 엔드포인트에서 호출)

        Args:
            mdn: 차량 번호(MDN)
            terminal_id: 단말기 ID
            manufacture_id: 제조사 ID
            packet_version: 패킷 버전
            device_id: 장치 ID
            device_firmware_version: 장치 펌웨어 버전

        Returns:
            bool: 성공 여부
        """
        # 에뮬레이터 매니저의 MDN 설정
        self.emulator_manager.mdn = mdn

        # 에뮬레이터 매니저에 등록
        success = self.emulator_manager.start_emulator(
            terminal_id, manufacture_id, packet_version, 
            device_id, device_firmware_version
        )

        if not success:
            print(f"[ERROR] 에뮬레이터 {mdn} 등록 실패")
            return False

        print(f"[INFO] 에뮬레이터 {mdn} 등록 완료")

        # 차량 시동 시작
        self.start_vehicle(mdn)

        return True

    def stop_emulator(self, mdn: str) -> bool:
        """
        에뮬레이터 중지 (API 엔드포인트에서 호출)

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            bool: 성공 여부
        """
        print(f"[DEBUG] stop_emulator 호출됨 - MDN: {mdn}")

        # 차량 시동 종료
        if self.emulator_manager.is_emulator_active(mdn):
            print(f"[DEBUG] 에뮬레이터 활성화 상태 - 시동 종료 시작 - MDN: {mdn}")
            stop_vehicle_result = self.stop_vehicle(mdn)
            print(f"[DEBUG] 시동 종료 {'성공' if stop_vehicle_result else '실패'} - MDN: {mdn}")
        else:
            print(f"[WARNING] 에뮬레이터가 이미 비활성화 상태입니다 - MDN: {mdn}")

        # 에뮬레이터 비활성화
        print(f"[DEBUG] 에뮬레이터 비활성화 시작 - MDN: {mdn}")
        success = self.emulator_manager.stop_emulator(mdn)

        if not success:
            print(f"[ERROR] 에뮬레이터 {mdn} 비활성화 실패")
            return False

        print(f"[INFO] 에뮬레이터 {mdn} 비활성화 완료")

        # 백엔드 전송 대기 로그 개수 확인
        pending_logs = self.log_storage_manager.count_pending_logs()
        total_pending = sum(pending_logs.values())
        print(f"[DEBUG] 현재 백엔드 전송 대기 로그 개수: 총 {total_pending}개 (GPS: {pending_logs['gps']}, 전원: {pending_logs['power']}, 지오펜스: {pending_logs['geofence']}) - MDN: {mdn}")

        # 미전송 로그 처리 (종료 전에 로그 전송 시도)
        if total_pending > 0:
            print(f"[INFO] 종료 전 미전송 로그 처리 시작 - MDN: {mdn}")
            self.log_storage_manager.process_pending_logs()

            # 처리 후 남은 로그 확인
            after_pending = self.log_storage_manager.count_pending_logs()
            after_total = sum(after_pending.values())
            print(f"[INFO] 종료 전 미전송 로그 처리 완료 - 처리 전: {total_pending}개, 처리 후: {after_total}개")

            if after_total < total_pending:
                print(f"[SUCCESS] {total_pending - after_total}개의 로그가 성공적으로 전송됨")
            else:
                print(f"[WARNING] 모든 로그 전송 실패 또는 새 로그 추가됨")

        return True

    #
    # 로그 처리 메서드
    #

    def process_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        수신된 GPS 로그 데이터 처리

        Args:
            log_data: GPS 로그 요청 데이터

        Returns:
            bool: 처리 성공 여부
        """
        # 에뮬레이터 존재 여부 확인
        if not self.emulator_manager.is_emulator_exists(log_data.mdn):
            print(f"[ERROR] 존재하지 않는 에뮬레이터입니다: {log_data.mdn}")
            return False

        # GPS 로그 저장
        return self.store_gps_log(log_data.mdn, log_data)

    def process_power_log(self, log_data: PowerLogRequest) -> bool:
        """
        수신된 시동 로그 데이터 처리

        Args:
            log_data: 시동 로그 요청 데이터

        Returns:
            bool: 처리 성공 여부
        """
        # 에뮬레이터 존재 여부 확인
        if not self.emulator_manager.is_emulator_exists(log_data.mdn):
            print(f"[ERROR] 존재하지 않는 에뮬레이터입니다: {log_data.mdn}")
            return False

        # 시동 로그 저장
        return self.store_power_log(log_data.mdn, log_data)

    def get_unsent_logs(self, mdn: str) -> list:
        """
        특정 MDN에 대한 미전송 로그 목록 조회

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            list: 미전송 로그 목록
        """
        # 각 핸들러에서 미전송 로그 수집
        gps_logs = self.log_storage_manager.gps_handler.get_pending_logs(mdn)
        power_logs = self.log_storage_manager.power_handler.get_pending_logs(mdn)
        geofence_logs = self.log_storage_manager.geofence_handler.get_pending_logs(mdn)

        # 모든 로그 합치기
        all_logs = gps_logs + power_logs + geofence_logs
        return all_logs

    #
    # 미전송 로그 관련 메서드 (후방 호환성 유지)
    #

    def store_unsent_gps_log(self, mdn: str, log_data: GpsLogRequest) -> bool:
        """
        미전송 GPS 로그 저장 (후방 호환용)

        Args:
            mdn: 차량 번호(MDN)
            log_data: GPS 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.store_gps_log(mdn, log_data)

    def store_unsent_power_log(self, mdn: str, log_data: PowerLogRequest) -> bool:
        """
        미전송 시동 로그 저장 (후방 호환용)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 시동 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.store_power_log(mdn, log_data)

    def store_unsent_geofence_log(self, mdn: str, log_data: GeofenceLogRequest) -> bool:
        """
        미전송 지오펜스 로그 저장 (후방 호환용)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 지오펜스 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.store_geofence_log(mdn, log_data)

    def store_unsent_log(self, mdn: str, log_data, log_type: str = "gps") -> bool:
        """
        미전송 로그 저장 (후방 호환용)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 로그 데이터
            log_type: 로그 타입 ("gps", "power", "geofence")

        Returns:
            bool: 저장 성공 여부
        """
        return self.log_storage_manager.store_unsent_log(mdn, log_data, log_type)

    #
    # 백그라운드 전송 제어
    #

    def start_background_sender(self) -> bool:
        """
        백그라운드 로그 전송 시작

        Returns:
            bool: 성공 여부
        """
        return self.log_storage_manager.start_background_sender()

    def stop_background_sender(self) -> bool:
        """
        백그라운드 로그 전송 중지

        Returns:
            bool: 성공 여부
        """
        return self.log_storage_manager.stop_background_sender()

    def _process_collected_data(self, mdn: str, data_batch: List[Dict[str, Any]], store: bool = True) -> Optional[GpsLogRequest]:
        """
        실시간 데이터 수집 콜백 메서드
        EmulatorManager의 실시간 데이터 수집에서 호출되는 콜백 함수

        Args:
            mdn: 차량 번호(MDN)
            data_batch: 수집된 데이터 배치 (60초 또는 설정된 배치 크기만큼의 데이터)
            store: 생성된 로그를 저장소에 저장할지 여부

        Returns:
            Optional[GpsLogRequest]: 생성된 GPS 로그
        """
        if not data_batch or len(data_batch) == 0:
            print(f"[WARNING] 차량 {mdn}의 수집 데이터가 없습니다")
            return None

        print(f"[INFO] 차량 {mdn}의 {len(data_batch)}개 데이터 처리 중")

        # GPS 로그 생성 (기존 create_gps_log_from_collected_data 메서드 사용)
        gps_log = self.gps_generator.create_gps_log_from_collected_data(mdn, data_batch)
        if not gps_log:
            print(f"[ERROR] 차량 {mdn} GPS 로그 생성 실패")
            return None

        # 로그 저장
        if store:
            self.store_gps_log(mdn, gps_log)
            print(f"[INFO] 차량 {mdn} GPS 로그 저장 완료")

        return gps_log


# 싱글톤 인스턴스
data_generator = EmulatorDataGenerator()
