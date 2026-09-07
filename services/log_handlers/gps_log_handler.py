"""
GPS 로그 핸들러
GPS 위치 로그를 처리합니다.
"""

from typing import Union, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from models.emulator_data import GpsLogRequest, GpsLogItem, PowerLogRequest, GeofenceLogRequest
from .base_log_handler import BaseLogHandler

KST = ZoneInfo("Asia/Seoul")


def gps_timestamp(value: datetime) -> datetime:
    """The wire clock is KST. Legacy naive fixture times are explicitly interpreted as KST."""
    if not isinstance(value, datetime):
        raise ValueError("GPS observation timestamp is required")
    return value.replace(tzinfo=KST) if value.tzinfo is None else value.astimezone(KST)


def gps_packets(common: Dict[str, str], observations: List[tuple]) -> List[GpsLogRequest]:
    """Preserve observation order; the wire has min/sec overrides but no per-point date/hour."""
    packets = []
    items = []
    first = None
    for observed_at, item in observations:
        observed_at = gps_timestamp(observed_at)
        if items and (observed_at.strftime("%Y%m%d%H") != first.strftime("%Y%m%d%H") or len(items) == 600):
            packets.append(GpsLogRequest(**common, oTime=first.strftime("%Y%m%d%H%M%S"), cCnt=str(len(items)), cList=items))
            items = []
        if not items:
            first = observed_at
        items.append(item.model_copy(update={"min": str(observed_at.minute), "sec": str(observed_at.second)}))
    if items:
        packets.append(GpsLogRequest(**common, oTime=first.strftime("%Y%m%d%H%M%S"), cCnt=str(len(items)), cList=items))
    return packets


class GpsLogHandler(BaseLogHandler):
    """GPS 로그 처리 핸들러"""

    def __init__(self, max_storage_hours: int = 1, backend_url: str = "http://localhost:8080"):
        """
        GPS 로그 핸들러 초기화

        Args:
            max_storage_hours: 최대 로그 보관 시간 (시간) - GPS 로그는 1시간 보관 기본값
            backend_url: 백엔드 서버 URL
        """
        super().__init__(log_type="gps", max_storage_hours=max_storage_hours, backend_url=backend_url)

    # 로그 타입은 초기화 시 설정함

    @property
    def backend_endpoint(self) -> str:
        """백엔드 API 엔드포인트"""
        return "/api/logs/gps"

    def store_gps_log(self, mdn: str, gps_log: Union[GpsLogRequest, List[GpsLogRequest]]) -> bool:
        """
        GPS 로그 데이터를 저장

        Args:
            mdn: 차량 번호(MDN)
            gps_log: GPS 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        if isinstance(gps_log, list):
            # Evaluate every packet, even if one is rejected; BaseLogHandler owns per-packet retry state.
            results = [self.store_gps_log(mdn, packet) for packet in gps_log]
            return bool(results) and all(results)
        log_count = len(gps_log.cList) if hasattr(gps_log, 'cList') else 0
        print(f"[DEBUG] GPS 로그 저장 시도 - MDN: {mdn}, 항목 수: {log_count}")
        success = self.store_log(mdn, gps_log)

        if success:
            print(f"[DEBUG] GPS 로그 저장 성공 - MDN: {mdn}, 항목 수: {log_count}")
            print(f"[INFO] GPS 로그 저장 및 전송 큐 등록 완료 - MDN: {mdn}")
            print(f"[INFO] 현재 백엔드 전송 대기 로그 개수: {self.count_pending_logs(mdn)} - MDN: {mdn}")
        else:
            print(f"[ERROR] GPS 로그 저장 실패 - MDN: {mdn}")

        return success

    def batch_gps_data_points(self, mdn: str, data_points: List[Dict[str, Any]], emulator_info: Dict[str, Any]) -> List[GpsLogRequest]:
        """
        GPS 데이터 포인트를 배치로 묶어 로그 객체 생성

        Args:
            mdn: 차량 번호(MDN)
            data_points: GPS 데이터 포인트 목록
            emulator_info: 에뮬레이터 정보

        Returns:
            List[GpsLogRequest]: 날짜·시간 경계와 600개 상한을 지킨 packet 목록
        """
        if not data_points:
            print(f"[경고] 배치 처리할 GPS 데이터 없음 - MDN: {mdn}")
            return []

        timestamps = [gps_timestamp(point.get("timestamp")) for point in data_points]

        # cList 항목 생성
        c_list = []
        for point, timestamp in zip(data_points, timestamps):
            # GPS 좌표는 1,000,000을 곱하여 Java 백엔드 형식에 맞춤
            # 좌표가 없을 경우(gcd=0)에는 값을 0으로 설정
            if point.get("gcd") == "0":
                lat = "0"
                lon = "0"
            else:
                lat = str(int(point["latitude"] * 1000000))
                lon = str(int(point["longitude"] * 1000000))

            c_list_item = {
                "min": str(timestamp.minute),
                "sec": str(timestamp.second),
                "gcd": point["gcd"],                    # GPS 좌표계 코드
                "lat": lat,                             # 위도
                "lon": lon,                             # 경도
                "ang": str(point["heading"]),           # 방향각
                "spd": str(int(point["speed"])),        # 속도
                "sum": str(point["accumulated_distance"]),  # 체크섬(누적 거리)
                "bat": str(point["battery_level"])      # 배터리 레벨
            }
            c_list.append((timestamp, GpsLogItem(**c_list_item)))

        # GPS 로그 요청 객체 생성
        return gps_packets({"mdn": mdn, "tid": emulator_info["terminal_id"],
                            "mid": str(emulator_info["manufacture_id"]),
                            "pv": str(emulator_info["packet_version"]),
                            "did": str(emulator_info["device_id"])}, c_list)

    def _print_debug_log(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> None:
        """GPS 로그에 맞는 디버그 정보 출력"""
        if isinstance(log_data, GpsLogRequest) and hasattr(log_data, 'cList') and log_data.cList:
            print(f"[INFO] GPS packet 항목 수: {len(log_data.cList)}")
        else:
            print(f"[경고] 잘못된 로그 타입 또는 빈 데이터: GpsLogHandler에 {type(log_data).__name__} 타입 전달됨")
