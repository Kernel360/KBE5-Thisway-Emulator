"""
시동(전원) 로그 핸들러
시동 ON/OFF 로그를 처리합니다.
"""

from typing import Union
from models.emulator_data import PowerLogRequest, GpsLogRequest, GeofenceLogRequest
from .base_log_handler import BaseLogHandler


class PowerLogHandler(BaseLogHandler):
    """시동(전원) 로그 처리 핸들러"""

    def __init__(self, max_storage_hours: int = 24, backend_url: str = "http://localhost:8080"):
        """
        시동 로그 핸들러 초기화

        Args:
            max_storage_hours: 최대 로그 보관 시간 (시간) - 시동 로그는 24시간 보관 기본값
            backend_url: 백엔드 서버 URL
        """
        super().__init__(log_type="power", max_storage_hours=max_storage_hours, backend_url=backend_url, use_auth=False)

    # 로그 타입은 초기화 시 설정함

    @property
    def backend_endpoint(self) -> str:
        """백엔드 API 엔드포인트"""
        return "/api/logs/power"

    def store_power_log(self, mdn: str, power_log: PowerLogRequest) -> bool:
        """
        시동 로그 데이터를 저장

        Args:
            mdn: 차량 번호(MDN)
            power_log: 시동 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        # 로그 타입 결정 (시동 ON 또는 시동 OFF)
        log_type = "시동 ON" if power_log.onTime and not power_log.offTime else "시동 OFF" if power_log.offTime else "알 수 없음"

        print(f"[DEBUG] {log_type} 로그 저장 시도 - MDN: {mdn}, 시동 ON 시간: {power_log.onTime}, 시동 OFF 시간: {power_log.offTime}, 좌표: ({power_log.lat}, {power_log.lon})")
        success = self.store_log(mdn, power_log)

        if success:
            print(f"[DEBUG] {log_type} 로그 저장 성공 - MDN: {mdn}, 시동 ON 시간: {power_log.onTime}, 시동 OFF 시간: {power_log.offTime}")
            print(f"[INFO] {log_type} 로그 저장 및 전송 큐 등록 완료 - MDN: {mdn}")
            print(f"[INFO] 현재 백엔드 전송 대기 로그 개수: {self.count_pending_logs(mdn)} - MDN: {mdn}")
        else:
            print(f"[ERROR] {log_type} 로그 저장 실패 - MDN: {mdn}")

        return success

    def _print_debug_log(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> None:
        """Power 로그에 맞는 디버그 정보 출력"""
        if isinstance(log_data, PowerLogRequest):
            power_log = log_data
            log_type = "시동 ON" if power_log.onTime and not power_log.offTime else "시동 OFF" if power_log.offTime else "알 수 없음"
            print(f"[디버깅] Power 로그({log_type}): {power_log.mdn}, 시동 ON 시간: {power_log.onTime}, 시동 OFF 시간: {power_log.offTime}, 좌표: ({power_log.lat}, {power_log.lon}), GPS 상태: {power_log.gcd}")
        else:
            print(f"[경고] 잘못된 로그 타입: PowerLogHandler에 {type(log_data).__name__} 타입 전달됨")
