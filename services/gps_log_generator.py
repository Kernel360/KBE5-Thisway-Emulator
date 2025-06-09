import random
import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from models.emulator_data import GpsLogRequest, GpsLogItem
from services.emulator_manager import EmulatorManager

class GpsLogGenerator:
    """GPS 로그 데이터 생성 담당 클래스"""
    
    def __init__(self, emulator_manager: EmulatorManager):
        self.emulator_manager = emulator_manager
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        두 지점 간의 거리를 미터 단위로 계산 (Haversine 공식)
        
        Args:
            lat1: 시작 위도
            lon1: 시작 경도
            lat2: 종료 위도
            lon2: 종료 경도
        """
        R = 6371000  # 지구 반경 (미터)
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        
        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        
        return distance
    
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
        if not self.emulator_manager.is_emulator_active(mdn):
            return None
            
        emulator = self.emulator_manager.active_emulators[mdn]
        current_time = datetime.now()
        
        # API 규격: oTime은 'yyyyMMddHHmm' 형식 (연도 4자리, 초 제외)
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
        
        # generate_full이 True면 60개 데이터 생성, False면 1개만 생성
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
                
                # 현실적인 움직임 구현 (80m 이하 거리)
                attempts = 0
                while not valid_movement and attempts < 5:
                    # 랜덤 위치 변화 (차량 움직임 시뮬레이션)
                    lat_adj = last_valid_lat + random.uniform(-0.0001, 0.0001)
                    lon_adj = last_valid_lon + random.uniform(-0.0001, 0.0001)
                    
                    # 거리 계산 (미터 단위)
                    distance = self.calculate_distance(last_valid_lat, last_valid_lon, lat_adj, lon_adj)
                    
                    # 초당 80m 이하 움직임만 허용
                    if distance <= 80:
                        valid_movement = True
                        # 누적 거리 계산
                        accumulated_distance += distance
                        last_valid_lat = lat_adj
                        last_valid_lon = lon_adj
                    
                    attempts += 1
                
                # 위도/경도를 문자열로 변환 (백엔드에서 1,000,000으로 이미 나누므로 스케일링하지 않음)
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
        return self.process_gps_log(log_data)
        

    def create_gps_log_from_collected_data(self, mdn: str, collected_data: List[Dict]) -> GpsLogRequest:
        """
        실시간으로 수집된 GPS 데이터를 구조화된 로그로 변환
        
        Args:
            mdn: 차량 번호
            collected_data: 실시간으로 수집된 데이터 목록
        """
        if not mdn or not collected_data or mdn not in self.emulator_manager.active_emulators:
            return None
        
        emulator = self.emulator_manager.active_emulators[mdn]
        current_time = datetime.now()
        
        # 기본 필드 설정
        gps_log = GpsLogRequest(
            mdn=mdn,
            tid=emulator["terminal_id"],
            mid=str(emulator["manufacture_id"]),
            pv=str(emulator["packet_version"]),
            did=str(emulator["device_id"]),
            oTime=current_time.strftime("%Y%m%d%H%M"),
            cCnt=str(len(collected_data)),
            cList=[]
        )
        
        # 수집된 데이터로 GPS 로그 항목 생성
        for i, data in enumerate(collected_data):
            # 실제 시간 데이터를 활용하여 항목 생성
            item_time = data["timestamp"].strftime("%S")
            latitude = data["latitude"]
            longitude = data["longitude"]
            angle = data["angle"]
            speed = data["speed"]
            battery = data["battery"]
            
            # GPS 좌표에 1,000,000을 곱하여 정수 형태로 변환
            lat_int = int(float(latitude) * 1000000)
            lon_int = int(float(longitude) * 1000000)
            
            # 체크섬 값 계산 (3개 값의 합)
            checksum = lat_int + lon_int + int(angle)
            
            # GPS 상태 코드 - 항상 정상('A')으로 설정
            gps_status = "A"  # GPS가 정상 작동 중임을 나타냄
            
            gps_log.cList.append(
                GpsLogItem(
                    sec=item_time,  # 초 단위
                    gcd=gps_status,  # GPS 상태 코드 ('A': 정상, 'V': 비정상, '0': 미장착)
                    lat=str(lat_int),  # 위도 (1,000,000 곱한 정수 형태)
                    lon=str(lon_int),  # 경도 (1,000,000 곱한 정수 형태)
                    ang=str(int(angle)),  # 방향각
                    spd=str(int(speed)),  # 속도 (km/h)
                    bat=str(int(battery)),  # 배터리 레벨
                    sum=str(checksum)  # 체크섬
                )
            )
        
        return gps_log

    def process_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        수신된 GPS 로그 데이터 처리
        
        Args:
            log_data: GPS 로그 요청 데이터
        """
        try:
            # 로그 데이터 처리 로직
            mdn = log_data.mdn
            
            # 활성화된 에뮬레이터가 있는 경우 상태 업데이트
            if mdn in self.emulator_manager.active_emulators:
                # 마지막 위치 업데이트 (마지막 유효 항목 기준)
                if log_data.cList and len(log_data.cList) > 0:
                    # 60초 데이터 중 마지막 유효한 항목 찾기
                    valid_items = [item for item in log_data.cList 
                                if item.lat != "0" and item.lon != "0" and item.gcd != "0"]
                    
                    if valid_items:
                        last_item = valid_items[-1]  # 마지막 유효 항목
                        try:
                            lat = float(last_item.lat)  # 스케일링 변환 제거
                            lon = float(last_item.lon)
                            
                            # 현재 에뮬레이터 위치와 로그 위치 간 거리 계산
                            current_lat = self.emulator_manager.active_emulators[mdn]["last_latitude"]
                            current_lon = self.emulator_manager.active_emulators[mdn]["last_longitude"]
                            distance = self.calculate_distance(current_lat, current_lon, lat, lon)
                            
                            # 위치 및 누적 거리 업데이트
                            self.emulator_manager.update_emulator_position(mdn, lat, lon, distance)
                        except (ValueError, TypeError):
                            print(f"Warning: Invalid lat/lon format in GPS log for MDN {mdn}")
                            
            return True
        except Exception as e:
            print(f"Error processing GPS log: {e}")
            return False
