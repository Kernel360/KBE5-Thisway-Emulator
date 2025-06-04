from fastapi import APIRouter, HTTPException, Path
from services.data_generator import data_generator
from models.emulator_data import VehicleData
from typing import Dict, Any

router = APIRouter(prefix="/api/emulator", tags=["emulator"])

@router.post("/{mdn}/start")
async def start_emulator(mdn: str = Path(..., description="Mobile Device Number")):
    """특정 MDN에 대한 에뮬레이터 시작"""
    # 실제 구현에서는 데이터베이스에서 에뮬레이터 세부 정보를 가져옴
    # 지금은 하드코딩된 값 또는 Java 백엔드에서 가져온 값 사용
    
    # 이 값들은 일반적으로 데이터베이스에서 가져옴
    terminal_id = f"TERM-{mdn[-4:]}"
    manufacture_id = 1
    packet_version = 1
    device_id = 101
    device_firmware_version = "1.0.0"
    
    success = data_generator.start_emulator(
        mdn, terminal_id, manufacture_id, packet_version, 
        device_id, device_firmware_version
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="에뮬레이터 시작 실패")
    
    return {"status": "started", "mdn": mdn}

@router.post("/{mdn}/stop")
async def stop_emulator(mdn: str = Path(..., description="Mobile Device Number")):
    """특정 MDN에 대한 에뮬레이터 중지"""
    success = data_generator.stop_emulator(mdn)
    
    if not success:
        raise HTTPException(status_code=404, detail="에뮬레이터를 찾을 수 없거나 이미 중지됨")
    
    return {"status": "stopped", "mdn": mdn}

@router.get("/{mdn}/data")
async def get_emulator_data(mdn: str = Path(..., description="Mobile Device Number")):
    """에뮬레이터에서 현재 데이터 가져오기"""
    data = data_generator.get_emulator_data(mdn)
    
    if not data:
        raise HTTPException(status_code=404, detail="에뮬레이터를 찾을 수 없거나 활성화되지 않음")
    
    return data
