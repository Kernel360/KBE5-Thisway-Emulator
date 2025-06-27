import argparse
import atexit
import sys

# 기존 서비스 가져오기
from services.data_generator import EmulatorDataGenerator
from services.log_storage_manager import LogStorageManager, get_data_collection_config

# 데이터 생성기의 싱글톤 인스턴스 생성
data_generator = EmulatorDataGenerator()

# 로그 저장 관리자 싱글톤 인스턴스 생성
# 로그는 즉시 전송되며, 실패한 로그는 300초(5분)마다 재시도
log_storage_manager = LogStorageManager(send_interval_seconds=300)

class EmulatorCLI:
    """단일 에뮬레이터를 위한 명령줄 인터페이스"""

    def __init__(self):
        self.running = True
        self.current_mdn = None

    def start_emulator(self, mdn: str, terminal_id: str = "A001", 
                      manufacture_id: int = 6, packet_version: int = 5, 
                      device_id: int = 1, device_firmware_version: str = "1.0.0"):
        """에뮬레이터 시작"""
        # 이미 실행 중인 에뮬레이터가 있으면 중지
        if self.current_mdn:
            print(f"이미 실행 중인 에뮬레이터 {self.current_mdn}를 중지합니다.")
            print("에뮬레이터는 GPS 주기정보 전송 종료 시 자동으로 중지됩니다.")
            # 테스트 목적으로 에뮬레이터 상태 직접 변경
            data_generator.emulator_manager.is_active = False
            # 현재 MDN 초기화
            self.current_mdn = None

        success = data_generator.start_emulator(
            mdn, terminal_id, manufacture_id, packet_version, 
            device_id, device_firmware_version
        )

        if success:
            self.current_mdn = mdn
            print(f"MDN: {mdn}로 에뮬레이터를 시작했습니다")
            return True
        else:
            print(f"MDN: {mdn}로 에뮬레이터 시작에 실패했습니다")
            return False


    def generate_gps_log(self, mdn: str = None, realtime: bool = False, store: bool = True):
        """GPS 로그 데이터 생성"""
        # mdn이 제공되지 않으면 현재 MDN 사용
        if mdn is None:
            mdn = self.current_mdn

        if not mdn:
            print("오류: 활성화된 에뮬레이터가 없습니다. 먼저 에뮬레이터를 시작하세요.")
            return False

        # 에뮬레이터가 존재하고 활성화되어 있는지 확인
        if not data_generator.emulator_manager.is_emulator_exists(mdn):
            print(f"오류: MDN {mdn}에 대한 에뮬레이터가 존재하지 않습니다")
            return False

        if not data_generator.emulator_manager.is_emulator_active(mdn):
            print(f"오류: 에뮬레이터가 활성화되어 있지 않습니다")
            return False

        # 실시간 모드 처리
        if realtime:
            # 실시간 데이터 수집이 이미 실행 중인지 확인
            if data_generator.emulator_manager.data_timer:
                print("실시간 데이터 수집이 이미 활성화되어 있습니다")
                return True

            # 먼저 카카오 API에서 경로 데이터를 가져와 설정 (추가된 부분)
            print("[INFO] 실시간 데이터 수집 전 카카오 API 경로 데이터 설정 중...")
            gps_log = data_generator.generate_gps_log(mdn, generate_full=True)
            if gps_log:
                print(f"[INFO] 카카오 API 경로 데이터 설정 성공 - {len(gps_log.cList)}개 포인트")
            else:
                print("[WARNING] 카카오 API 경로 데이터 설정 실패 - 실시간 위치 업데이트가 제한될 수 있습니다")

            # 설정 파일에서 데이터 수집 설정 가져오기
            interval_sec, batch_size, send_interval_sec = get_data_collection_config()

            # 실시간 데이터 수집 시작
            data_generator.emulator_manager.start_realtime_data_collection(
                callback=data_generator._process_collected_data,
                interval_sec=interval_sec,
                batch_size=batch_size,
                send_interval_sec=send_interval_sec
            )

            print(f"실시간 데이터 수집을 시작했습니다. 데이터는 {interval_sec}초마다 수집되며, {send_interval_sec}초마다 전송됩니다.")
            return True
        else:
            # 60초 데이터가 포함된 단일 GPS 로그 생성
            gps_log = data_generator.generate_gps_log(mdn, generate_full=True)

            if not gps_log:
                print("GPS 로그 생성에 실패했습니다")
                return False

            # 요청된 경우 로그 저장
            if store:
                data_generator.log_storage_manager.store_unsent_log(mdn, gps_log)
                print(f"{len(gps_log.cList)}개 항목의 GPS 로그를 생성하고 저장했습니다")
            else:
                print(f"{len(gps_log.cList)}개 항목의 GPS 로그를 생성했습니다 (저장 안 함)")

            return True

    def get_pending_logs(self, mdn: str = None):
        """대기 중인 로그 가져오기"""
        # mdn이 제공되지 않으면 현재 MDN 사용
        if mdn is None:
            mdn = self.current_mdn

        if not mdn:
            print("오류: 활성화된 에뮬레이터가 없습니다. 먼저 에뮬레이터를 시작하세요.")
            return None

        # 에뮬레이터가 존재하는지 확인
        if not data_generator.emulator_manager.is_emulator_exists(mdn):
            print(f"오류: MDN {mdn}에 대한 에뮬레이터가 존재하지 않습니다")
            return None

        # 전송되지 않은 로그 가져오기
        unsent_logs = data_generator.get_unsent_logs(mdn)
        print(f"{len(unsent_logs)}개의 대기 중인 로그를 찾았습니다")
        return unsent_logs

    def show_emulator_status(self):
        """현재 에뮬레이터 상태 표시"""
        if not self.current_mdn:
            print("활성화된 에뮬레이터가 없습니다")
            return None

        emulator = data_generator.emulator_manager
        if not emulator.is_active:
            print(f"에뮬레이터 상태: 비활성")
            return None

        print(f"에뮬레이터 상태: 활성")
        print(f"MDN: {emulator.mdn}")
        print(f"위치: ({emulator.last_latitude}, {emulator.last_longitude})")
        print(f"마지막 업데이트: {emulator.last_update}")

        return {
            "mdn": emulator.mdn,
            "is_active": emulator.is_active,
            "position": (emulator.last_latitude, emulator.last_longitude),
            "last_update": emulator.last_update
        }

    def run_interactive(self):
        """대화형 모드에서 에뮬레이터 실행"""
        print("디스웨이 에뮬레이터 CLI")
        print("사용 가능한 명령어를 보려면 'help'를 입력하세요")

        while self.running:
            try:
                command = input("> ").strip()

                if command == "exit" or command == "quit":
                    self.running = False
                    print("종료 중...")
                    break

                elif command == "help":
                    self.print_help()

                elif command.startswith("start "):
                    # 형식: start <mdn>
                    parts = command.split()
                    if len(parts) < 2:
                        print("오류: MDN이 누락되었습니다. 사용법: start <mdn>")
                    else:
                        mdn = parts[1]
                        self.start_emulator(mdn)

                elif command == "stop":
                    # 현재 실행 중인 에뮬레이터 중지
                    if self.current_mdn:
                        print(f"에뮬레이터 {self.current_mdn}를 중지합니다.")
                        print("에뮬레이터는 GPS 주기정보 전송 종료 시 자동으로 중지됩니다.")
                        # 테스트 목적으로 에뮬레이터 상태 직접 변경
                        data_generator.emulator_manager.is_active = False
                        # 현재 MDN 초기화
                        self.current_mdn = None
                    else:
                        print("중지할 활성 에뮬레이터가 없습니다")

                elif command == "generate":
                    # 현재 에뮬레이터에 대한 GPS 로그 생성
                    self.generate_gps_log()

                elif command == "generate realtime":
                    # 현재 에뮬레이터에 대한 실시간 GPS 로그 생성
                    self.generate_gps_log(realtime=True)

                elif command == "generate nostore":
                    # 현재 에뮬레이터에 대한 GPS 로그 생성 (저장 안 함)
                    self.generate_gps_log(store=False)

                elif command == "pending":
                    # 현재 에뮬레이터에 대한 대기 중인 로그 가져오기
                    self.get_pending_logs()

                elif command == "status":
                    # 현재 에뮬레이터 상태 표시
                    self.show_emulator_status()

                else:
                    print(f"알 수 없는 명령어: {command}")
                    self.print_help()

            except KeyboardInterrupt:
                print("\n종료 중...")
                self.running = False
                break
            except Exception as e:
                print(f"오류: {str(e)}")

    def print_help(self):
        """도움말 정보 출력"""
        print("사용 가능한 명령어:")
        print("  start <mdn>                - 지정된 MDN으로 에뮬레이터 시작 및 자동 실행")
        print("  stop                       - 현재 에뮬레이터 중지 (참고: 실제 중지는 GPS 주기정보 전송 종료 시 자동으로 처리됨)")
        print("  generate                   - GPS 로그 데이터 생성")
        print("  generate realtime          - 실시간 GPS 데이터 수집 시작")
        print("  generate nostore           - 저장하지 않고 GPS 로그 데이터 생성")
        print("  pending                    - 대기 중인 로그 가져오기")
        print("  status                     - 현재 에뮬레이터 상태 표시")
        print("  help                       - 이 도움말 메시지 표시")
        print("  exit, quit                 - 프로그램 종료")

def parse_arguments():
    """명령줄 인수 파싱"""
    parser = argparse.ArgumentParser(description="디스웨이 에뮬레이터")

    # 다양한 명령어를 위한 하위 파서 추가
    subparsers = parser.add_subparsers(dest="command", help="실행할 명령어")

    # 에뮬레이터 시작 명령어 (자동 실행 모드)
    start_parser = subparsers.add_parser("start", help="에뮬레이터 시작 및 자동 실행")
    start_parser.add_argument("mdn", help="모바일 기기 번호")

    # 에뮬레이터 개별 시작 명령어
    start_emulator_parser = subparsers.add_parser("start_emulator", help="에뮬레이터 시작")
    start_emulator_parser.add_argument("mdn", help="모바일 기기 번호")

    # 에뮬레이터 중지 명령어
    subparsers.add_parser("stop", help="에뮬레이터 중지 (참고: 실제 중지는 GPS 주기정보 전송 종료 시 자동으로 처리됨)")

    # GPS 로그 생성 명령어
    generate_parser = subparsers.add_parser("generate", help="GPS 로그 데이터 생성")
    generate_parser.add_argument("--realtime", action="store_true", help="실시간 데이터 수집 활성화")
    generate_parser.add_argument("--no-store", dest="store", action="store_false", help="생성된 로그 저장하지 않음")
    generate_parser.set_defaults(store=True)

    # 대기 중인 로그 가져오기 명령어
    subparsers.add_parser("pending", help="대기 중인 로그 가져오기")

    # 에뮬레이터 상태 확인 명령어
    subparsers.add_parser("status", help="현재 에뮬레이터 상태 표시")

    # 대화형 모드
    subparsers.add_parser("interactive", help="대화형 모드에서 실행")

    return parser.parse_args()

def main():
    """메인 진입점"""
    # 애플리케이션 시작 시 백그라운드 로그 전송 스레드 시작
    log_storage_manager.start_background_sender()
    print("[INFO] 애플리케이션 시작: 백그라운드 로그 전송 스레드가 시작되었습니다.")

    args = parse_arguments()
    cli = EmulatorCLI()

    if args.command == "start":
        print(f"[INFO] 에뮬레이터 자동 시작 - MDN: {args.mdn}")
        success = cli.start_emulator(
            mdn=args.mdn,
            terminal_id=f"TERM-{args.mdn[-4:]}",
            manufacture_id=1,
            packet_version=1,
            device_id=101,
            device_firmware_version="1.0.0"
        )
        if success:
            print(f"[INFO] 에뮬레이터 자동 시작 완료 - MDN: {args.mdn}")

            # 에뮬레이터 시작 후 자동으로 실시간 GPS 데이터 수집 시작
            cli.generate_gps_log(mdn=args.mdn, realtime=True)
            print(f"[INFO] 실시간 GPS 데이터 수집 자동 시작 완료 - MDN: {args.mdn}")

            # 프로그램이 계속 실행되도록 유지
            print("[INFO] 에뮬레이터가 백그라운드에서 실행 중입니다. 종료하려면 Ctrl+C를 누르세요.")
            try:
                # 무한 루프로 프로그램 실행 유지
                import time
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n[INFO] 사용자에 의해 프로그램이 중단되었습니다.")
                # 에뮬레이터 중지 (이전에는 cli.stop_emulator(args.mdn)를 호출했지만 이제는 직접 처리)
                print(f"에뮬레이터 {args.mdn}를 중지합니다.")
                print("에뮬레이터는 GPS 주기정보 전송 종료 시 자동으로 중지됩니다.")
                # 테스트 목적으로 에뮬레이터 상태 직접 변경
                data_generator.emulator_manager.is_active = False
                # CLI의 현재 MDN 초기화
                if cli.current_mdn == args.mdn:
                    cli.current_mdn = None
        else:
            print(f"[경고] 에뮬레이터 자동 시작 실패 - MDN: {args.mdn}")

    elif args.command == "start_emulator":
        cli.start_emulator(args.mdn)

    elif args.command == "stop":
        # 이전에는 cli.stop_emulator()를 호출했지만 이제는 직접 처리
        if cli.current_mdn:
            print(f"에뮬레이터 {cli.current_mdn}를 중지합니다.")
            print("에뮬레이터는 GPS 주기정보 전송 종료 시 자동으로 중지됩니다.")
            # 테스트 목적으로 에뮬레이터 상태 직접 변경
            data_generator.emulator_manager.is_active = False
            # 현재 MDN 초기화
            cli.current_mdn = None
        else:
            print("중지할 활성 에뮬레이터가 없습니다")

    elif args.command == "generate":
        cli.generate_gps_log(realtime=args.realtime, store=args.store)

    elif args.command == "pending":
        cli.get_pending_logs()

    elif args.command == "status":
        cli.show_emulator_status()

    elif args.command == "interactive" or args.command is None:
        cli.run_interactive()

    else:
        print(f"알 수 없는 명령어: {args.command}")
        return 1

    return 0

# 프로그램 종료 시 백그라운드 스레드 정리
def cleanup():
    log_storage_manager.stop_background_sender()
    print("[INFO] 프로그램 종료: 리소스 정리 완료")

# 정상 종료 시 cleanup 함수 실행
atexit.register(cleanup)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[INFO] 사용자에 의해 프로그램이 중단되었습니다.")
        cleanup()
        sys.exit(0)
