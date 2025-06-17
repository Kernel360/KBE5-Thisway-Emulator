#!/usr/bin/env python3
"""
Simple test script for the Thisway Emulator.
This script tests basic functionality of the emulator.
"""

import time
import random
from services.data_generator import data_generator

def test_emulator():
    """Test basic emulator functionality"""
    print("디스웨이 에뮬레이터 테스트 중...")

    # Generate a random MDN for testing
    test_mdn = str(random.randint(1000000000, 9999999999))
    print(f"테스트 MDN 사용: {test_mdn}")

    # Test 1: Start emulator
    print("\n테스트 1: 에뮬레이터 시작 중...")
    success = data_generator.start_emulator(
        mdn=test_mdn,
        terminal_id="TEST",
        manufacture_id=6,
        packet_version=5,
        device_id=1,
        device_firmware_version="1.0.0"
    )

    if success:
        print("✓ 에뮬레이터가 성공적으로 시작되었습니다")
    else:
        print("✗ 에뮬레이터 시작에 실패했습니다")
        return False

    # Test 2: Generate GPS log
    print("\n테스트 2: GPS 로그 생성 중...")
    gps_log = data_generator.generate_gps_log(test_mdn, generate_full=True)

    if gps_log and len(gps_log.cList) == 60:
        print(f"✓ {len(gps_log.cList)}개 항목의 GPS 로그를 생성했습니다")
        print(f"  첫 번째 위치: ({gps_log.cList[0].lat}, {gps_log.cList[0].lon})")
        print(f"  마지막 위치: ({gps_log.cList[-1].lat}, {gps_log.cList[-1].lon})")
    else:
        print("✗ GPS 로그 생성에 실패했습니다")
        return False

    # Test 3: Store log
    print("\n테스트 3: 로그 저장 중...")
    success = data_generator.log_storage_manager.store_unsent_log(test_mdn, gps_log)

    if success:
        print("✓ 로그가 성공적으로 저장되었습니다")
    else:
        print("✗ 로그 저장에 실패했습니다")
        return False

    # Test 4: Retrieve pending logs
    print("\n테스트 4: 대기 중인 로그 검색 중...")
    pending_logs = data_generator.get_unsent_logs(test_mdn)

    if pending_logs and len(pending_logs) > 0:
        print(f"✓ {len(pending_logs)}개의 대기 중인 로그를 검색했습니다")
    else:
        print("✗ 대기 중인 로그 검색에 실패했습니다")
        return False

    # Test 5: Start realtime data collection
    print("\n테스트 5: 실시간 데이터 수집 시작 중...")

    # Define a callback function to receive collected data
    def test_callback(mdn, data_list):
        print(f"MDN {mdn}에 대해 {len(data_list)}개의 데이터 포인트를 수신했습니다")

    # Start realtime data collection
    data_generator.emulator_manager.start_realtime_data_collection(
        callback=test_callback,
        interval_sec=0.1,  # Use a short interval for testing
        batch_size=5       # Use a small batch size for testing
    )

    print("실시간 데이터 수집 대기 중 (2초)...")
    time.sleep(2)  # Wait for some data to be collected

    if data_generator.emulator_manager.data_timer:
        print("✓ 실시간 데이터 수집이 성공적으로 시작되었습니다")
    else:
        print("✗ 실시간 데이터 수집 시작에 실패했습니다")
        return False

    # Test 6: Stop realtime data collection
    print("\n테스트 6: 실시간 데이터 수집 중지 중...")
    data_generator.emulator_manager.stop_realtime_data_collection()

    if not data_generator.emulator_manager.data_timer:
        print("✓ 실시간 데이터 수집이 성공적으로 중지되었습니다")
    else:
        print("✗ 실시간 데이터 수집 중지에 실패했습니다")
        return False

    # Test 7: Stop emulator
    print("\n테스트 7: 에뮬레이터 중지 중...")
    success = data_generator.stop_emulator()

    if success:
        print("✓ 에뮬레이터가 성공적으로 중지되었습니다")
    else:
        print("✗ 에뮬레이터 중지에 실패했습니다")
        return False

    print("\n모든 테스트가 성공적으로 통과했습니다!")
    return True

if __name__ == "__main__":
    test_emulator()
