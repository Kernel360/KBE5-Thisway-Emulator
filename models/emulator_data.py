from pydantic import BaseModel
from typing import Optional
from datetime import datetime

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
