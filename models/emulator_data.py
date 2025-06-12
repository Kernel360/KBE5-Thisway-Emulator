from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class GpsLogItem(BaseModel):
    sec: str = Field(..., description="초 단위 시간")
    gcd: str = Field(..., description="GPS 좌표계 코드")
    lat: str = Field(..., description="위도")
    lon: str = Field(..., description="경도")
    ang: str = Field(..., description="방향각")
    spd: str = Field(..., description="속도")
    sum: str = Field(..., description="체크섬")
    bat: str = Field(..., description="배터리 레벨")

class GpsLogRequest(BaseModel):
    mdn: str = Field(..., description="단말기 고유 번호(Mobile Device Number)")
    tid: str = Field(..., description="단말기 ID(Terminal ID)")
    mid: str = Field(..., description="제조사 ID(Manufacturer ID)")
    pv: str = Field(..., description="패킷 버전(Packet Version)")
    did: str = Field(..., description="장치 ID(Device ID)")
    oTime: str = Field(..., description="발생 시간")
    cCnt: str = Field(..., description="로그 항목 수(Count)")
    cList: List[GpsLogItem] = Field(..., description="GPS 로그 항목 목록")

class PowerLogRequest(BaseModel):
    mdn: str = Field(..., description="단말기 고유 번호(Mobile Device Number)")
    tid: str = Field(..., description="단말기 ID(Terminal ID)")
    mid: str = Field(..., description="제조사 ID(Manufacturer ID)")
    pv: str = Field(..., description="패킷 버전(Packet Version)")
    did: str = Field(..., description="장치 ID(Device ID)")
    onTime: str = Field(..., description="시동 ON 시간 (형식: yyMMddHHmm)")
    offTime: str = Field("", description="시동 OFF 시간 (형식: yyMMddHHmm)")
    gcd: str = Field(..., description="GPS 상태 ('A':정상, 'V':비정상, '0':미작동, 'P':시동ON시 GPS 수신 비정상)")
    lat: str = Field(..., description="위도")
    lon: str = Field(..., description="경도")
    ang: str = Field(..., description="방향각 (0~365)")
    spd: str = Field(..., description="속도 (0~255 km/h)")
    sum: str = Field(..., description="누적 주행 거리 (m단위)")

class GeofenceLogRequest(BaseModel):
    mdn: str = Field(..., description="단말기 고유 번호(Mobile Device Number)")
    tid: str = Field(..., description="단말기 ID(Terminal ID)")
    mid: str = Field(..., description="제조사 ID(Manufacturer ID)")
    pv: str = Field(..., description="패킷 버전(Packet Version)")
    did: str = Field(..., description="장치 ID(Device ID)")
    oTime: str = Field(..., description="발생 시간 (형식: yyMMddHHmm)")
    geoGrpId: str = Field(..., description="지오펜스 그룹 ID")
    geoPId: str = Field(..., description="지오펜스 포인트 ID")
    evtVal: str = Field(..., description="이벤트 값 (1: 진입, 2: 이탈)")
    gcd: str = Field(..., description="GPS 상태 ('A':정상, 'V':비정상, '0':미작동)")
    lat: str = Field(..., description="위도")
    lon: str = Field(..., description="경도")
    ang: str = Field(..., description="방향각 (0~365)")
    spd: str = Field(..., description="속도 (0~255 km/h)")
    sum: str = Field(..., description="누적 주행 거리 (m단위)")

class LogResponse(BaseModel):
    code: str = "000"
    message: str = "Success"
    mdn: str

class VehicleData(BaseModel):
    mdn: str
    terminal_id: str
    manufacture_id: int
    packet_version: int
    device_id: int
    device_firmware_version: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    heading: Optional[int] = None
    battery_level: Optional[float] = None
    engine_temperature: Optional[float] = None
    timestamp: datetime = datetime.now()
