"""
시동(Power) 로그 생성기
차량 시동 ON/OFF 관련 로그 데이터를 생성하는 클래스
"""

import random
from datetime import datetime
from typing import Dict, Any, Optional

from models.emulator_data import PowerLogRequest
from services.log_generators.base_log_generator import BaseLogGenerator

class PowerLogGenerator(BaseLogGenerator):
    """시동 로그 데이터 생성 담당 클래스

    시동 ON 규칙:
    - 최초 차량이 Key-On 시점에만 전송
    - GPS 미수신 상태라면 GPS 상태 'P'로 설정, 직전 위치 사용
    - 최초 시동 ON은 위경도 값 없이 상태값 'V' 또는 '0'으로 전송
    - 누적 거리는 직전 시동 OFF 값과 일치

    시동 OFF 규칙:
    - 차량이 Key-Off 시점에만 전송
    - GPS 미수신 상태라면 GPS 상태 'P'로 설정
    - 위경도 값은 가장 최근 잡힌 위경도 값 사용
    - 누적 거리는 다음 시동 ON 값과 일치
    - 시동 OFF 데이터는 그 전에 발생한 시동 ON의 발생 시간이 포함
    """

    def generate_power_log(self, mdn: str, power_on: bool = True) -> Optional[PowerLogRequest]:
        """
        시동 로그 요청 데이터 생성

        Args:
            mdn: 차량 번호 (단말기 번호)
            power_on: 시동 ON(True) 또는 OFF(False)

        Returns:
            PowerLogRequest: 시동 로그 요청 객체
        """
        # 에뮬레이터가 없거나 활성화되지 않은 경우
        emulator = self.get_emulator(mdn)
        if not emulator:
            return None

        current_time = datetime.now()

        # API 규격: onTime/offTime은 'yyyymmddhhmmss' 형식
        time_str = current_time.strftime("%Y%m%d%H%M%S")

        # 누적 주행 거리
        total_distance = self.emulator_manager.get_accumulated_distance(mdn)
        sum_val = str(int(total_distance))

        # 위치 및 GPS 상태 정보 설정
        gps_status = "A"  # 기본값: 정상
        lat = 0.0
        lon = 0.0
        ang = "0"
        spd = "0"

        # 시동 ON 처리
        if power_on:
            # 위치 정보: 직전 시동 OFF의 위치 사용
            if mdn in self.emulator_manager.last_positions:
                last_pos = self.emulator_manager.last_positions[mdn]
                lat = last_pos["latitude"]
                lon = last_pos["longitude"]

                # GPS 상태 결정 (random으로 95% 정상 처리)
                is_gps_normal = random.random() < 0.95
                gps_status = "A" if is_gps_normal else "P"
            else:
                # 최초 시동 ON인 경우 - 위경도 없이 상태값만 설정
                gps_status = "V"  # GPS 비정상 또는 미장착
                # 임의의 초기 위치 설정
                lat = emulator["last_latitude"]
                lon = emulator["last_longitude"]

            # 시동 ON 시 속도는 항상 0
            spd = "0"
        # 시동 OFF 처리
        else:
            # 최근 위치 정보 사용
            lat = emulator["last_latitude"]
            lon = emulator["last_longitude"]

            # GPS 상태 결정 (random으로 95% 정상 처리)
            is_gps_normal = random.random() < 0.95
            gps_status = "A" if is_gps_normal else "P"

            # 시동 OFF 시 직전 속도 반영
            spd = str(random.randint(0, 100))  # 현실적인 속도 범위로 조정

        # 방향각 (규격: 0~365)
        ang = str(random.randint(0, 365))

        # 시동 ON/OFF 시간 처리
        on_time = ""
        off_time = ""

        if power_on:
            # 시동 ON 시간만 설정
            on_time = time_str

            # 시동 ON 시간 저장 (향후 시동 OFF 시 필요)
            # 단일 에뮬레이터 모드에서는 직접 속성으로 저장
            self.emulator_manager.last_power_on_time = time_str
            # 이전 버전과의 호환성을 위한 active_emulators 업데이트
            self.emulator_manager.active_emulators = {mdn: self.emulator_manager.get_emulator_dict()}
        else:
            # 시동 OFF 시간 및 직전 시동 ON 시간 설정
            off_time = time_str

            # 직전 시동 ON 시간 가져오기
            # 단일 에뮬레이터 모드에서는 직접 속성에서 가져옴
            if hasattr(self.emulator_manager, "last_power_on_time") and self.emulator_manager.last_power_on_time:
                on_time = self.emulator_manager.last_power_on_time
            else:
                # 시동 ON 시간이 없는 경우 현재 시간에서 1시간 전으로 설정 (임의의 값)
                from datetime import timedelta
                on_time = (datetime.now() - timedelta(hours=1)).strftime("%Y%m%d%H%M%S")
                print(f"[WARNING] 시동 ON 시간이 없어 임의 값으로 설정: {on_time}")

        # 위도/경도 값을 소수점 6자리로 제한하고 1,000,000 곱하기
        lat_value = round(lat, 6)
        lon_value = round(lon, 6)

        # 시동 로그 요청 생성
        power_log = PowerLogRequest(
            mdn=mdn,
            # API 규격: tid는 차량관제에서 'A001'로 고정
            tid="A001",
            # API 규격: mid는 CNSLink는 '6' 값 사용
            mid="6",
            # API 규격: pv는 M2M 버전이 5이므로 '5'로 고정
            pv="5",
            # API 규격: did는 GPS로만 운영함으로 '1'로 고정
            did="1",
            # 시동 ON/OFF 시간
            onTime=on_time,
            offTime=off_time,
            # GPS 상태
            gcd=gps_status,
            # 위치 정보 - 소수점 6자리로 제한하고 1,000,000 곱하기
            lat=str(int(lat_value * 1000000)),
            lon=str(int(lon_value * 1000000)),
            ang=ang,
            spd=spd,
            sum=sum_val
        )

        # 시동 상태 업데이트
        emulator["is_active"] = power_on

        # 시동 OFF 시 현재 위치 저장 (향후 시동 ON시 사용)
        if not power_on:
            self.emulator_manager.last_positions[mdn] = {
                "latitude": emulator["last_latitude"],
                "longitude": emulator["last_longitude"],
                "timestamp": current_time
            }

            # 시동 OFF 시 최신 누적 거리 가져오기
            total_distance = self.emulator_manager.get_accumulated_distance(mdn)
            sum_val = str(int(total_distance))

            # 에뮬레이터 매니저에 최종 누적 거리 업데이트
            self.emulator_manager.update_accumulated_distance(int(total_distance), mdn)

        return power_log

    def process_power_log(self, log_data: PowerLogRequest) -> bool:
        """
        시동 로그 데이터 처리

        Args:
            log_data: 시동 로그 데이터

        Returns:
            bool: 처리 성공 여부
        """
        # MDN 추출
        mdn = log_data.mdn

        # 시동 ON/OFF 여부 확인
        is_power_on = bool(log_data.onTime and not log_data.offTime)

        if is_power_on:
            # 시동 ON 처리
            print(f"[INFO] 차량 {mdn} 시동 ON 처리 (시간: {log_data.onTime})")
        else:
            # 시동 OFF 처리
            print(f"[INFO] 차량 {mdn} 시동 OFF 처리 (시간: {log_data.offTime}, 누적 거리: {log_data.sum}m)")

        # 로그 처리 성공 여부 반환 (실제 저장은 EmulatorDataGenerator에서 수행)
        return True
