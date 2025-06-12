"""
지오펜스 로그 생성기
지오펜스 진입/이탈 관련 로그 데이터를 생성하는 클래스
"""

import random
from datetime import datetime
from typing import Dict, Any, Optional

from models.emulator_data import GeofenceLogRequest
from services.log_generators.base_log_generator import BaseLogGenerator

class GeofenceLogGenerator(BaseLogGenerator):
    """지오펜스 로그 데이터 생성 담당 클래스"""

    def generate_geofence_log(self, mdn: str, geo_grp_id: str, geo_p_id: str, 
                             evt_val: str = "1") -> Optional[GeofenceLogRequest]:
        """
        지오펜스 로그 요청 데이터 생성

        Args:
            mdn: 차량 번호 (단말기 번호)
            geo_grp_id: 지오펜스 그룹 ID
            geo_p_id: 지오펜스 포인트 ID
            evt_val: 이벤트 값 (1: 진입, 2: 이탈)

        Returns:
            GeofenceLogRequest: 지오펜스 로그 요청 객체
        """
        # 에뮬레이터가 없거나 활성화되지 않은 경우
        emulator = self.get_emulator(mdn)
        if not emulator:
            return None

        current_time = datetime.now()

        # API 규격: oTime은 'yyyyMMddHHmmss' 형식
        time_str = current_time.strftime("%Y%m%d%H%M%S")

        # 현재 위치 데이터
        lat = emulator["last_latitude"]
        lon = emulator["last_longitude"]

        # 위도/경도 값을 소수점 6자리로 제한
        lat_value = round(lat, 6)
        lon_value = round(lon, 6)

        # GPS 상태 ('A': 정상, 'V': 비정상, '0': 미장착)
        # 대부분 정상(95%)으로 설정
        gps_status = "A" if random.random() < 0.95 else ("V" if random.random() < 0.9 else "0")

        # 방향각 (규격: 0~365)
        ang = str(random.randint(0, 365))

        # 속도 (규격: 0~255 km/h)
        spd = "0" if not emulator["is_active"] else str(random.randint(0, 255))

        # 누적 주행 거리
        total_distance = self.emulator_manager.get_accumulated_distance(mdn)
        sum_val = str(int(total_distance))

        # 지오펜스 로그 요청 생성
        geofence_log = GeofenceLogRequest(
            mdn=mdn,
            # API 규격: tid는 차량관제에서 'A001'로 고정
            tid="A001",
            # API 규격: mid는 CNSLink는 '6' 값 사용
            mid="6",
            # API 규격: pv는 M2M 버전이 5이므로 '5'로 고정
            pv="5",
            # API 규격: did는 GPS로만 운영함으로 '1'로 고정
            did="1",
            oTime=time_str,
            geoGrpId=geo_grp_id,
            geoPId=geo_p_id,
            evtVal=evt_val,
            # GPS 상태
            gcd=gps_status,
            # 위치 정보 - 소수점 6자리로 제한하고 1,000,000 곱하기
            lat=str(int(lat_value * 1000000)),
            lon=str(int(lon_value * 1000000)),
            ang=ang,
            spd=spd,
            sum=sum_val
        )

        # 지오펜스 이벤트 후 누적 거리 업데이트
        self.emulator_manager.update_accumulated_distance(int(total_distance), mdn)

        return geofence_log

    def process_geofence_log(self, log_data: GeofenceLogRequest) -> bool:
        """
        지오펜스 로그 데이터 처리

        Args:
            log_data: 지오펜스 로그 데이터

        Returns:
            bool: 처리 성공 여부
        """
        # 향후 처리 로직 추가
        return True
