"""
GPS 로그 생성기
GPS 관련 로그 데이터를 생성하는 클래스
"""

import random
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from models.emulator_data import GpsLogRequest, GpsLogItem
from services.log_generators.base_log_generator import BaseLogGenerator

class GpsLogGenerator(BaseLogGenerator):
    """GPS 로그 데이터 생성 담당 클래스"""

    def generate_gps_log(self, mdn: str, generate_full: bool = True) -> Optional[GpsLogRequest]:
        """
        GPS 로그 요청 데이터 생성 (0~59초 데이터)

        Args:
            mdn: 차량 번호 (단말기 번호)
            generate_full: True면 60개의 전체 데이터 생성, False면 스냅샷용 1개만 생성

        Returns:
            GpsLogRequest: GPS 로그 요청 객체
        """
        # 에뮬레이터가 없거나 활성화되지 않은 경우
        emulator = self.get_emulator(mdn)
        if not emulator:
            return None

        current_time = datetime.now()

        # API 규격: oTime은 'yyyyMMddHHmm' 형식 (연도 4자리, 초 미포함)
        time_str = current_time.strftime("%Y%m%d%H%M")

        # 기준 위치 데이터
        base_lat = emulator["last_latitude"]
        base_lon = emulator["last_longitude"]

        # GPS 상태 결정 (90% 확률로 'A', 8% 확률로 'V', 2% 확률로 '0')
        gps_status_rand = random.random()
        if gps_status_rand > 0.10:
            gps_status = "A"  # 정상
        elif gps_status_rand > 0.02:
            gps_status = "V"  # 비정상
        else:
            gps_status = "0"  # 미장착

        # 로그 항목 생성 
        log_items = []
        last_valid_lat = base_lat
        last_valid_lon = base_lon
        accumulated_distance = 0

        # generate_full이 True면 60개 데이터 생성(0-59초), False면 1개만 생성
        # 항상 0~59초의 총 60개 데이터를 전송해야 함(GPS 값이 없더라도 '0'으로 설정)
        sec_range = range(60) if generate_full else [0]

        for i in sec_range:
            # GPS 상태가 '0'이면 위치 데이터 없음
            if gps_status == "0":
                lat_str = "0"
                lon_str = "0"
                ang_str = "0"
                spd_str = "0"
                sum_str = str(int(self.emulator_manager.get_accumulated_distance(mdn)))

                # 배터리 전압 (실제값 × 10, 단위: V, 범위: 0~9999)
                battery_voltage = random.uniform(11.5, 14.5)  # 자동차 배터리 일반 전압 범위
                bat_str = str(int(battery_voltage * 10))
            else:
                # 이전 위치에서 랜덤한 거리 이동
                # 초당 최대 20m 속도를 가정 (80m 이상이면 스킵하도록 제한)
                valid_movement = False
                lat_adj = last_valid_lat
                lon_adj = last_valid_lon
                distance = 0

                # 현실적인 움직임 구현 - 항상 유효한 움직임을 보장
                attempts = 0
                while not valid_movement and attempts < 5:
                    # 랜덤 위치 변화 (차량 움직임 시뮬레이션)
                    lat_adj = last_valid_lat + random.uniform(-0.0001, 0.0001)
                    lon_adj = last_valid_lon + random.uniform(-0.0001, 0.0001)

                    # 거리 계산 (미터 단위)
                    distance = self.calculate_distance(last_valid_lat, last_valid_lon, lat_adj, lon_adj)

                    # 
                    # 핵심 요구사항: 초간 이동 거리가 80m 이상이면 해당 구간은 스킵하여 계산
                    # 

                    # 초당 80m 이하 움직임만 허용 - 80m 이상은 비정상적 이동으로 간주하고 스탕
                    if distance <= 80:
                        valid_movement = True
                        # 누적 거리 계산
                        accumulated_distance += distance
                        last_valid_lat = lat_adj
                        last_valid_lon = lon_adj
                    else:
                        # 초당 80m 이상 이동 거리인 경우 스킵
                        continue

                    attempts += 1

                # 위도/경도를 문자열로 변환
                lat_str = str(lat_adj)
                lon_str = str(lon_adj)

                # 방향각 (규격: 0~365)
                ang_str = str(random.randint(0, 365))

                # 속도 (규격: 0~255 km/h)
                speed = random.randint(0, 255) if emulator["is_active"] else 0
                spd_str = str(speed)

                # 누적 주행 거리 (현재까지의 주행거리 + 이번 이동거리)
                total_distance = self.emulator_manager.get_accumulated_distance(mdn) + int(accumulated_distance)
                # 9,999,999m(약 10,000km)로 제한
                if total_distance > 9999999:
                    total_distance = 9999999
                sum_str = str(int(total_distance))

                # 배터리 전압 (실제값 × 10, 단위: V, 범위: 0~9999)
                battery_voltage = random.uniform(11.5, 14.5)  # 자동차 배터리 일반 전압 범위
                bat_str = str(int(battery_voltage * 10))

            # GpsLogItem 생성
            log_item = GpsLogItem(
                sec=str(i),  # 0~59초 중 해당 시간
                gcd=gps_status,
                lat=lat_str,
                lon=lon_str,
                ang=ang_str,
                spd=spd_str,
                sum=sum_str,
                bat=bat_str
            )
            log_items.append(log_item)

        # 마지막 위치로 에뮬레이터 업데이트
        if log_items and gps_status != "0":
            # 누적 거리 업데이트
            self.emulator_manager.update_emulator_position(
                mdn, 
                last_valid_lat, 
                last_valid_lon, 
                accumulated_distance
            )

        # GPS 로그 요청 생성
        gps_log = GpsLogRequest(
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
            cCnt=str(len(log_items)),
            cList=log_items
        )

        return gps_log

    def process_received_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        수신된 GPS 로그 데이터 처리

        Args:
            log_data: GPS 로그 요청 데이터
        """
        # 로그 처리 로직 (향후 구현)
        return True

    def create_gps_log_from_collected_data(self, mdn: str, collected_data: List[Dict]) -> GpsLogRequest:
        """
        실시간으로 수집된 GPS 데이터를 구조화된 로그로 변환

        Args:
            mdn: 차량 번호
            collected_data: 실시간으로 수집된 데이터 목록
        """
        if not mdn or not collected_data:
            return None

        emulator = self.get_emulator(mdn)
        if not emulator:
            return None

        current_time = datetime.now()
        time_str = current_time.strftime("%Y%m%d%H%M")

        # 디버깅 정보 출력
        print(f"[DEBUG] 수집된 데이터 첫 항목 키: {list(collected_data[0].keys()) if collected_data else 'None'}")

        # 누적 거리 계산을 위한 변수
        total_distance = self.emulator_manager.get_accumulated_distance(mdn)

        log_items = []
        for i, data in enumerate(collected_data):
            # 이전 데이터 포인트와의 거리 계산 및 누적
            distance = 0
            angle = data.get("angle", 0)  # 기본값 사용
            speed = data.get("speed", 0)  # 기본값 사용

            if i > 0:
                prev_data = collected_data[i-1]
                prev_lat = prev_data.get("latitude", 0)
                prev_lon = prev_data.get("longitude", 0)
                curr_lat = data.get("latitude", 0)
                curr_lon = data.get("longitude", 0)
                prev_speed = prev_data.get("speed", 0)
                prev_angle = prev_data.get("angle", 0)

                # 거리 계산 (미터 단위)
                distance = self.calculate_distance(prev_lat, prev_lon, curr_lat, curr_lon)

                # 시간 간격 계산 (초 단위)
                prev_time = prev_data.get("timestamp")
                curr_time = data.get("timestamp")
                time_diff = 1.0  # 기본값 1초

                if prev_time and curr_time:
                    time_diff = (curr_time - prev_time).total_seconds()
                    if time_diff <= 0:
                        time_diff = 1.0  # 시간 차이가 없거나 음수인 경우 기본값 사용

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
                    lat2_rad = math.radians(curr_lat)
                    lon2_rad = math.radians(curr_lon)

                    # 방위각 계산 (북쪽이 0도, 시계 방향)
                    y = math.sin(lon2_rad - lon1_rad) * math.cos(lat2_rad)
                    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon2_rad - lon1_rad)
                    angle_rad = math.atan2(y, x)
                    current_angle = (math.degrees(angle_rad) + 360) % 360

                    # 급격한 방향 변화 방지를 위한 스무딩 (이전 방향의 80%, 현재 방향의 20%)
                    # 단, 방향 차이가 180도 이상이면 스무딩 없이 새 방향 사용
                    angle_diff = abs(current_angle - prev_angle)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff

                    if angle_diff < 180:
                        angle = prev_angle * 0.8 + current_angle * 0.2
                    else:
                        angle = current_angle
                else:
                    angle = prev_angle  # 이동이 없으면 이전 방향 유지

                # 누적 거리 업데이트 (80m 이상 이동은 비정상으로 간주하고 제외)
                if distance <= 80:
                    total_distance += distance

            # 위도/경도 값을 소수점 6자리로 제한하고 1,000,000 곱하기
            lat_value = round(data.get("latitude", 0), 6)
            lon_value = round(data.get("longitude", 0), 6)

            log_item = GpsLogItem(
                sec=str(i),
                gcd="A",  # 기본값 A (정상)
                lat=str(int(lat_value * 1000000)),  # 소수점 6자리로 제한하고 1,000,000 곱하기
                lon=str(int(lon_value * 1000000)),  # 소수점 6자리로 제한하고 1,000,000 곱하기
                ang=str(int(angle)),  # 계산된 방향각 사용
                spd=str(int(speed)),  # 계산된 속도 사용
                sum=str(int(total_distance)),  # 계산된 누적 거리 사용
                bat=str(int(data.get("battery", 0)))  # battery 키 사용
            )
            log_items.append(log_item)

        # 최종 누적 거리를 에뮬레이터 매니저에 업데이트
        self.emulator_manager.update_accumulated_distance(int(total_distance), mdn)

        gps_log = GpsLogRequest(
            mdn=mdn,
            tid="A001",
            mid="6",
            pv="5",
            did="1",
            oTime=time_str,
            cCnt=str(len(log_items)),
            cList=log_items
        )

        return gps_log
