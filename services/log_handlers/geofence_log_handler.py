"""
지오펜스 로그 핸들러
지오펜스 이벤트 로그를 처리합니다.
"""

from typing import Union
from models.emulator_data import GpsLogRequest, PowerLogRequest, GeofenceLogRequest
from .base_log_handler import BaseLogHandler


class GeofenceLogHandler(BaseLogHandler):
    """지오펜스 로그 처리 핸들러"""
    
    def __init__(self, max_storage_hours: int = 1, backend_url: str = "http://localhost:8080"):
        """
        지오펜스 로그 핸들러 초기화
        
        Args:
            max_storage_hours: 최대 로그 보관 시간 (시간)
            backend_url: 백엔드 서버 URL
        """
        super().__init__(log_type="geofence", max_storage_hours=max_storage_hours, backend_url=backend_url, use_auth=False)
    
    # 로그 타입은 초기화 시 설정함
        
    @property
    def backend_endpoint(self) -> str:
        """백엔드 API 엔드포인트"""
        return "/api/logs/geofence"
    
    def store_geofence_log(self, mdn: str, geofence_log: GeofenceLogRequest) -> bool:
        """
        지오펜스 로그 데이터를 저장
        
        Args:
            mdn: 차량 번호(MDN)
            geofence_log: 지오펜스 로그 데이터
            
        Returns:
            bool: 저장 성공 여부
        """
        print(f"[DEBUG] 지오펜스 로그 저장 시도 - MDN: {mdn}, 지오펜스 ID: {geofence_log.geoPId}, 이벤트: {geofence_log.evtVal}")
        success = self.store_log(mdn, geofence_log)
        
        if success:
            print(f"[DEBUG] 지오펜스 로그 저장 성공 - MDN: {mdn}")
            print(f"[INFO] 지오펜스 로그 저장 및 전송 큐 등록 완료 - MDN: {mdn}")
            print(f"[INFO] 현재 백엔드 전송 대기 로그 개수: {self.count_pending_logs(mdn)} - MDN: {mdn}")
        else:
            print(f"[ERROR] 지오펜스 로그 저장 실패 - MDN: {mdn}")
            
        return success
    
    def _print_debug_log(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> None:
        """지오펜스 로그에 맞는 디버그 정보 출력"""
        if isinstance(log_data, GeofenceLogRequest):
            geofence_log = log_data
            print(f"[디버깅] 지오펜스 로그: {geofence_log.mdn}, 그룹 ID: {geofence_log.geoGrpId}, 포인트 ID: {geofence_log.geoPId}, 이벤트: {geofence_log.evtVal}, 좌표: ({geofence_log.lat}, {geofence_log.lon})")
        else:
            print(f"[경고] 잘못된 로그 타입: GeofenceLogHandler에 {type(log_data).__name__} 타입 전달됨")
