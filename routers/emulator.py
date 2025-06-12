from fastapi import APIRouter, HTTPException, Path, Query
from services.data_generator import data_generator
from models.emulator_data import VehicleData, GpsLogRequest, LogResponse, PowerLogRequest
from typing import Dict, Any

router = APIRouter(tags=["emulator"])

@router.post("/api/emulator/{mdn}/start")
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

@router.post("/api/emulator/{mdn}/stop")
async def stop_emulator(mdn: str = Path(..., description="Mobile Device Number")):
    """특정 MDN에 대한 에뮬레이터 중지"""
    success = data_generator.stop_emulator(mdn)
    
    if not success:
        raise HTTPException(status_code=404, detail="에뮬레이터를 찾을 수 없거나 이미 중지됨")
    
    return {"status": "stopped", "mdn": mdn}

# 조회 API 제거 (사용하지 않음)

@router.post("/api/logs/gps")
async def receive_gps_logs(request: GpsLogRequest):
    """
    GPS 로그 데이터 수신 엔드포인트
    
    요청 본문에 GPS 로그 데이터를 포함하여 전송해주세요.
    60초의 데이터를 하나의 전문으로 구성해야 합니다.
    """
    # 로그 정보 출력
    print(f"Received GPS logs from MDN: {request.mdn}")
    print(f"Log time: {request.oTime}, Item count: {request.cCnt}")
    
    # 로그 데이터 유효성 검사
    if not request.cList or len(request.cList) == 0:
        raise HTTPException(status_code=400, detail="GPS 로그 데이터 항목이 비어있습니다")
    
    # 60개의 데이터가 아닌 경우 경고 출력 (유연한 처리를 위해 에러는 바로 발생시키지 않음)
    if len(request.cList) != 60:
        print(f"Warning: Expected 60 log items, but got {len(request.cList)}")
    
    # 로그 데이터 처리
    success = data_generator.process_gps_log(request)
    if not success:
        # 실패한 로그 데이터 저장 (추후 재전송을 위해)
        data_generator.store_unsent_log(request.mdn, request)
        raise HTTPException(status_code=500, detail="로그 데이터 처리 중 오류가 발생했습니다")
    
    # 응답 반환
    return LogResponse(mdn=request.mdn)

@router.post("/api/logs/power")
async def receive_power_logs(request: PowerLogRequest):
    """
    차량 시동 정보 수신 엔드포인트
    
    시동 ON 데이터 처리를 위한 엔드포인트입니다.
    시동 ON 이벤트 발생 시 호출됩니다.
    """
    # 로그 정보 출력
    print(f"Received Power log from MDN: {request.mdn}")
    print(f"Power ON time: {request.onTime}, GPS status: {request.gcd}")
    
    # 로그 데이터 처리
    success = data_generator.process_power_log(request)
    if not success:
        # 실패한 로그 데이터 저장 (추후 재전송을 위해)
        data_generator.store_unsent_power_log(request.mdn, request)
        raise HTTPException(status_code=500, detail="시동 로그 데이터 처리 중 오류가 발생했습니다")
    
    # 응답 반환
    return LogResponse(mdn=request.mdn)

@router.get("/api/logs/pending/{mdn}")
async def get_pending_logs(mdn: str = Path(..., description="Mobile Device Number")):
    """
    특정 MDN에 대해 전송되지 못한 대기 중인 로그 데이터 가져오기
    """
    # 에뮬레이터 활성 상태 확인
    if not data_generator.emulator_manager.is_emulator_exists(mdn):
        raise HTTPException(status_code=404, detail=f"MDN {mdn}에 대한 에뮬레이터가 없습니다")
    
    # 미전송 로그 가져오기
    unsent_logs = data_generator.get_unsent_logs(mdn)
    
    # 결과 반환
    return {
        "mdn": mdn,
        "pending_count": len(unsent_logs),
        "logs": unsent_logs if len(unsent_logs) > 0 else []
    }

@router.post("/api/logs/generate/{mdn}")
async def generate_gps_log(
    mdn: str = Path(..., description="Mobile Device Number"),
    realtime: bool = Query(False, description="실시간 데이터 생성 모드 활성화 (60초마다 데이터 전송)"),
    store: bool = Query(True, description="생성된 로그를 미전송 저장소에 저장"),
):
    """
    테스트용 GPS 로그 생성 API
    
    - realtime=True: 실시간 모드 활성화 (60초마다 자동으로 데이터 수집 및 전송)
    - realtime=False: 즉시 60초분 데이터 일괄 생성
    - store=True: 생성된 로그를 미전송 저장소에 저장 (백엔드로 전송 대기)
    """
    # 에뮬레이터 활성 상태 확인
    if not data_generator.emulator_manager.is_emulator_exists(mdn):
        raise HTTPException(status_code=404, detail=f"MDN {mdn}에 대한 에뮬레이터가 없습니다")
    
    if not data_generator.emulator_manager.is_emulator_active(mdn):
        raise HTTPException(status_code=400, detail=f"MDN {mdn}의 에뮬레이터가 활성화되지 않았습니다")
    
    # 실시간 모드인 경우 실시간 데이터 수집 시작
    if realtime:
        # 실시간 데이터 수집이 이미 진행 중인지 확인
        if mdn in data_generator.emulator_manager.data_timers:
            return {
                "message": f"MDN {mdn}의 실시간 데이터 수집이 이미 활성화되어 있습니다",
                "mdn": mdn,
                "mode": "realtime",
                "success": True
            }
        
        # 실시간 데이터 수집 시작
        data_generator.emulator_manager.start_realtime_data_collection(
            mdn=mdn,
            callback=data_generator._process_collected_data,
            interval_sec=1.0,
            batch_size=60
        )
        
        return {
            "message": f"MDN {mdn}의 실시간 데이터 수집을 시작했습니다. 60초마다 로그가 자동 생성됩니다.",
            "mdn": mdn,
            "mode": "realtime",
            "success": True
        }
    else:
        # 즉시 모드인 경우 60초 데이터가 포함된 GPS 로그 즉시 생성
        gps_log = data_generator.generate_gps_log(mdn, generate_full=True)
        
        if not gps_log:
            raise HTTPException(status_code=500, detail=f"GPS 로그 생성 실패")
        
        # 저장 옵션이 활성화된 경우 미전송 저장소에 저장
        if store:
            data_generator.log_storage_manager.store_unsent_log(mdn, gps_log)
        
        return gps_log
