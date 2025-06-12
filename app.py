from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import emulator
from services.log_storage_manager import LogStorageManager
import atexit

# 로그 저장 관리자 싱글톤 인스턴스 생성
# 로그는 즉시 전송되며, 실패한 로그는 300초(5분)마다 재시도
log_storage_manager = LogStorageManager(send_interval_seconds=300)

app = FastAPI(title="Vehicle Emulator API")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션 환경에서는 조정 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 포함
app.include_router(emulator.router)

@app.on_event("startup")
async def startup_event():
    # 애플리케이션 시작 시 백그라운드 로그 전송 스레드 시작
    log_storage_manager.start_background_sender()
    print("[INFO] 애플리케이션 시작: 백그라운드 로그 전송 스레드가 시작되었습니다.")

    # 애플리케이션 시작 시 자동으로 에뮬레이터 시작
    # 기본 MDN 설정 (여러 에뮬레이터를 시작하려면 추가 가능)
    default_mdn = "01012345678"
    try:
        from routers.emulator import data_generator
        success = data_generator.start_emulator(
            mdn=default_mdn,
            terminal_id=f"TERM-{default_mdn[-4:]}",
            manufacture_id=1,
            packet_version=1,
            device_id=101,
            device_firmware_version="1.0.0"
        )
        if success:
            print(f"[INFO] 에뮬레이터 자동 시작 완료 - MDN: {default_mdn}")

            # 에뮬레이터 시작 후 자동으로 실시간 GPS 데이터 수집 시작
            data_generator.emulator_manager.start_realtime_data_collection(
                mdn=default_mdn,
                callback=data_generator._process_collected_data,
                interval_sec=1.0,
                batch_size=60
            )
            print(f"[INFO] 실시간 GPS 데이터 수집 자동 시작 완료 - MDN: {default_mdn}")
        else:
            print(f"[경고] 에뮬레이터 자동 시작 실패 - MDN: {default_mdn}")
    except Exception as e:
        print(f"[오류] 에뮬레이터 자동 시작 중 예외 발생: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    # 애플리케이션 종료 시 백그라운드 로그 전송 스레드 중지
    log_storage_manager.stop_background_sender()
    print("[INFO] 애플리케이션 종료: 백그라운드 로그 전송 스레드가 중지되었습니다.")

# 프로그램 종료 시 백그라운드 스레드 정리
def cleanup():
    log_storage_manager.stop_background_sender()
    print("[INFO] 프로그램 종료: 리소스 정리 완료")

# 정상 종료 시 cleanup 함수 실행
atexit.register(cleanup)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8081, reload=True)
