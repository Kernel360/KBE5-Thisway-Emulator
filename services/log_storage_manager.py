"""
로그 저장 및 전송 관리자
각 로그 타입별 핸들러를 관리하고 백그라운드 전송 스레드를 운영합니다.
"""

import threading
import time
import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from models.emulator_data import GpsLogRequest, PowerLogRequest, GeofenceLogRequest
from services.log_handlers.gps_log_handler import GpsLogHandler
from services.log_handlers.power_log_handler import PowerLogHandler
from services.log_handlers.geofence_log_handler import GeofenceLogHandler

def get_backend_url():
    """
    백엔드 URL 설정 가져오기

    1. 환경 변수 BACKEND_URL 확인
    2. config.json 파일 확인
    3. 기본값 사용

    Returns:
        str: 백엔드 URL
    """
    # 기본 백엔드 URL
    default_backend_url = "http://localhost:8080"

    # 1. 환경 변수에서 백엔드 URL 확인
    backend_url = os.environ.get("BACKEND_URL", default_backend_url)

    # 2. 설정 파일에서 백엔드 URL 확인 (있는 경우)
    try:
        # 설정 파일이 있는지 확인
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                config = json.load(f)
                if "backend_url" in config:
                    backend_url = config["backend_url"]
                    print(f"[INFO] config.json에서 백엔드 URL 설정 로드: {backend_url}")
    except Exception as e:
        print(f"[경고] 설정 파일 읽기 실패: {str(e)}")

    return backend_url


class LogStorageManager:
    """
    미전송 로그 데이터 저장, 관리 및 전송 담당 클래스
    각 로그 타입별 핸들러를 생성하고 백그라운드 전송 스레드를 관리합니다.
    """

    def __init__(self, send_interval_seconds: int = 300):
        """
        로그 저장 관리자 초기화

        Args:
            send_interval_seconds: 백그라운드 전송 간격(초), 기본값은 300초(5분)
                                  로그는 즉시 전송되므로 백그라운드 전송은 실패한 로그 재시도용
        """
        # 백엔드 API 서버 URL (config.json 또는 환경 변수에서 가져옴)
        self.backend_url = get_backend_url()
        print(f"[설정] 백엔드 URL: {self.backend_url}")
        print(f"[설정] GPS 로그 엔드포인트: {self.backend_url}/api/logs/gps")
        print(f"[설정] 시동 로그 엔드포인트: {self.backend_url}/api/logs/power")
        print(f"[설정] 지오펜스 로그 엔드포인트: {self.backend_url}/api/logs/geofence")

        # 백엔드 연결 상태 확인
        try:
            import requests
            print(f"[설정] 백엔드 서버 연결 상태 확인 중...")
            response = requests.get(f"{self.backend_url}/api/auth/health", timeout=3)
            if response.status_code == 200:
                print(f"[설정] 백엔드 서버 연결 성공! 상태: {response.status_code}")
                self.backend_connection_status = "Connected"
            elif response.status_code == 401:
                print(f"[설정] 백엔드 서버 연결됨: 인증 필요 (401) - 인증 없이 진행합니다")
                self.backend_connection_status = "Connected (Auth Required)"
                # 인증 오류는 정상 연결로 간주 (인증 없이 로그 전송 시도 예정)
            else:
                print(f"[설정] 백엔드 서버 연결됨. 비정상 응답: {response.status_code}")
                self.backend_connection_status = f"Connected (Abnormal: {response.status_code})"
        except Exception as e:
            print(f"[설정] 백엔드 서버 연결 실패: {str(e)}")
            print(f"[설정] 유효한 URL인지 확인하세요: {self.backend_url}")
            self.backend_connection_status = f"Connection Failed: {str(e)}"

        # 로그 핸들러 초기화 - 즉시 전송 모드 활성화
        self.gps_handler = GpsLogHandler(max_storage_hours=1, backend_url=self.backend_url)
        self.power_handler = PowerLogHandler(max_storage_hours=24, backend_url=self.backend_url)
        self.geofence_handler = GeofenceLogHandler(max_storage_hours=1, backend_url=self.backend_url)

        # 로그 전송 간격 (초 단위) - 실패한 로그 재시도용
        self.send_interval_seconds = send_interval_seconds

        # 백엔드 연결 상태 로깅
        self.last_connection_attempt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 백그라운드 스레드 상태
        self.running = False
        self.sender_thread = None

        print(f"로그 저장 관리자 초기화 완료 - 즉시 전송 모드 활성화")
        print(f"백엔드 서버 상태: {self.backend_connection_status}")
        print(f"실패한 로그 재시도 간격: {self.send_interval_seconds}초")
        print(f"로그 보관 시간 - GPS: {self.gps_handler.max_storage_hours}시간, 시동: {self.power_handler.max_storage_hours}시간")

    #
    # 로그 저장 메서드
    #

    def store_gps_log(self, mdn: str, log_data: GpsLogRequest) -> bool:
        """
        GPS 로그 데이터 저장 (GpsLogHandler로 위임)

        Args:
            mdn: 차량 번호(MDN)
            log_data: GPS 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.gps_handler.store_gps_log(mdn, log_data)

    def store_power_log(self, mdn: str, log_data: PowerLogRequest) -> bool:
        """
        시동 로그 데이터 저장 (PowerLogHandler로 위임)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 시동 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.power_handler.store_power_log(mdn, log_data)

    def store_geofence_log(self, mdn: str, log_data: GeofenceLogRequest) -> bool:
        """
        지오펜스 로그 데이터 저장 (GeofenceLogHandler로 위임)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 지오펜스 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        return self.geofence_handler.store_geofence_log(mdn, log_data)

    #
    # 후방 호환성 메서드 (기존 코드와의 호환성 유지)
    #

    def store_unsent_log(self, mdn: str, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest], log_type: str = "gps") -> bool:
        """
        미전송 로그 데이터 저장 (후방 호환용)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 로그 데이터
            log_type: 로그 타입 ("gps", "power", "geofence")

        Returns:
            bool: 저장 성공 여부
        """
        if log_type == "gps" and isinstance(log_data, GpsLogRequest):
            return self.store_gps_log(mdn, log_data)
        elif log_type == "power" and isinstance(log_data, PowerLogRequest):
            return self.store_power_log(mdn, log_data)
        elif log_type == "geofence" and isinstance(log_data, GeofenceLogRequest):
            return self.store_geofence_log(mdn, log_data)
        else:
            print(f"[ERROR] 알 수 없는 로그 타입 또는 로그 데이터 불일치 - MDN: {mdn}, 타입: {log_type}, 데이터: {type(log_data).__name__}")
            return False

    def store_custom_log(self, mdn: str, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest], log_type: str) -> bool:
        """
        미전송 로그 데이터 저장 (후방 호환용)

        Args:
            mdn: 차량 번호(MDN)
            log_data: 저장할 로그 데이터
            log_type: 로그 타입 ("gps", "power", "geofence")

        Returns:
            bool: 저장 성공 여부
        """
        return self.store_unsent_log(mdn, log_data, log_type)

    #
    # 백엔드 전송 관련 메서드
    #

    def process_pending_logs(self) -> None:
        """모든 로그 핸들러의 미전송 로그 처리"""
        try:
            # 각 핸들러의 미전송 로그 처리 (모든 MDN에 대해)
            gps_count = self.gps_handler.process_all_pending_logs()
            power_count = self.power_handler.process_all_pending_logs()
            geofence_count = self.geofence_handler.process_all_pending_logs()

            if gps_count > 0 or power_count > 0 or geofence_count > 0:
                print(f"[INFO] 로그 처리 완료 - GPS: {gps_count}, 전원: {power_count}, 지오펜스: {geofence_count}개")
        except Exception as e:
            print(f"[ERROR] 미전송 로그 처리 중 오류: {str(e)}")
            import traceback
            print(traceback.format_exc())

    def count_pending_logs(self) -> Dict[str, int]:
        """
        각 로그 타입별 미전송 로그 개수 반환

        Returns:
            Dict[str, int]: 로그 타입별 미전송 로그 개수
        """
        try:
            # count_pending_logs 메서드로 변경 (count_all_pending_logs는 구현되지 않음)
            # 각 핸들러의 모든 MDN에 대한 로그 수 합산
            gps_count = sum([len(queue) for queue in self.gps_handler.pending_logs.values()])
            power_count = sum([len(queue) for queue in self.power_handler.pending_logs.values()])
            geofence_count = sum([len(queue) for queue in self.geofence_handler.pending_logs.values()])

            return {
                "gps": gps_count,
                "power": power_count,
                "geofence": geofence_count
            }
        except Exception as e:
            print(f"[ERROR] 미전송 로그 개수 조회 중 오류: {str(e)}")
            return {"gps": 0, "power": 0, "geofence": 0}

    def get_pending_logs_summary(self) -> Dict[str, Any]:
        """
        미전송 로그 요약 정보 반환

        Returns:
            Dict[str, Any]: 로그 타입별 미전송 로그 요약 정보
        """
        # count_pending_logs 메서드로 변경 (count_all_pending_logs는 구현되지 않음)
        counts = self.count_pending_logs()
        return {
            "gps_logs": counts["gps"],
            "power_logs": counts["power"], 
            "geofence_logs": counts["geofence"],
            "backend_status": self.backend_connection_status,
            "last_connection_attempt": self.last_connection_attempt
        }

    #
    # 백그라운드 스레드 관리 메서드
    #

    def start_background_sender(self) -> bool:
        """
        백그라운드 전송 스레드 시작

        Returns:
            bool: 스레드 시작 성공 여부
        """
        if self.sender_thread and self.sender_thread.is_alive():
            print("[INFO] 백그라운드 로그 전송 스레드가 이미 실행 중입니다.")
            return False

        self.running = True
        self.sender_thread = threading.Thread(target=self._background_sender_task, daemon=True)
        self.sender_thread.start()
        print("[INFO] 백그라운드 로그 전송 스레드를 시작했습니다.")
        return True

    def stop_background_sender(self) -> bool:
        """
        백그라운드 전송 스레드 중지

        Returns:
            bool: 스레드 중지 성공 여부
        """
        if not self.sender_thread or not self.sender_thread.is_alive():
            print("[INFO] 백그라운드 로그 전송 스레드가 실행 중이 아닙니다.")
            return False

        self.running = False
        self.sender_thread.join(timeout=5.0)
        if self.sender_thread.is_alive():
            print("[WARNING] 백그라운드 로그 전송 스레드가 완전히 종료되지 않았습니다.")
            return False

        print("[INFO] 백그라운드 로그 전송 스레드를 중지했습니다.")
        return True

    def _background_sender_task(self) -> None:
        """백그라운드 로그 전송 작업"""
        print("[INFO] 백그라운드 로그 전송 스레드가 시작되었습니다.")
        # 로그 전송 간격 명확하게 표시
        print(f"[INFO] 실패한 로그 재시도 간격: {self.send_interval_seconds}초")
        # 디버깅을 위해 현재 설정된 값 출력
        if self.send_interval_seconds != 300:
            print(f"[INFO] 기본값(300초)과 다른 재시도 간격이 설정되었습니다: {self.send_interval_seconds}초")

        # 초기 대기 시간
        print("[INFO] 초기 대기 후 로그 전송을 시작합니다...")
        time.sleep(5)  # 프로그램 시작 후 5초 후에 첫 전송 시도

        while self.running:
            try:
                # 현재 로그 카운트 출력
                pending_count = self.count_pending_logs()
                total_pending = sum(pending_count.values())
                if total_pending > 0:
                    print(f"[INFO] 미전송 로그 {total_pending}개 처리 시작 - GPS: {pending_count['gps']}, 전원: {pending_count['power']}, 지오펜스: {pending_count['geofence']}개")

                # 미전송 로그 처리
                self.process_pending_logs()

                # 처리 후 카운트 다시 확인
                after_count = self.count_pending_logs()
                after_total = sum(after_count.values())
                if total_pending > 0:
                    print(f"[INFO] 로그 전송 후 남은 로그: {after_total}개")
                    if after_total < total_pending:
                        print(f"[SUCCESS] {total_pending - after_total}개의 로그가 성공적으로 전송됨")
                    else:
                        print(f"[WARNING] 모든 로그 전송 실패 또는 새 로그 추가됨")

                # 시간 기록
                self.last_connection_attempt = time.strftime("%Y-%m-%d %H:%M:%S")

                # 다음 전송까지 대기
                print(f"[INFO] 다음 로그 전송까지 {self.send_interval_seconds}초 대기...")
                time.sleep(self.send_interval_seconds)
            except Exception as e:
                print(f"[ERROR] 백그라운드 로그 전송 중 예외 발생: {str(e)}")
                import traceback
                print(traceback.format_exc())
                time.sleep(self.send_interval_seconds)

        print("[INFO] 백그라운드 로그 전송 스레드가 종료되었습니다.")
