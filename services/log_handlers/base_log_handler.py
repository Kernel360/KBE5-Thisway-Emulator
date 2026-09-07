"""
기본 로그 핸들러 추상 클래스
모든 로그 핸들러의 기본 인터페이스를 정의합니다.
"""

import abc
import queue
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional, Union

from models.emulator_data import GpsLogRequest, PowerLogRequest, GeofenceLogRequest
from services.device_credentials import CredentialBinding, load_device_credential


class BaseLogHandler(abc.ABC):
    """로그 처리를 위한 기본 추상 클래스"""

    def __init__(self, log_type: str, max_storage_hours: int = 24, backend_url: str = "http://localhost:8080"):
        """
        로그 핸들러 초기화

        Args:
            log_type: 로그 타입 (예: 'gps', 'power', 'geofence')
            max_storage_hours: 최대 로그 보관 시간 (시간)
            backend_url: 백엔드 서버 URL
        """
        # 해당 로그 타입에 대한 미전송 로그를 저장하는 큐 (MDN별)
        self.pending_logs = {}  # MDN -> Queue
        # 큐 액세스를 위한 락
        self.queue_lock = threading.Lock()
        # 최대 저장 시간 (기본 24시간)
        self.max_storage_hours = max_storage_hours
        # 백엔드 API 서버 URL
        self.backend_url = backend_url
        # 로그 타입
        self.log_type = log_type

    @property
    @abc.abstractmethod
    def backend_endpoint(self) -> str:
        """백엔드 API 엔드포인트"""
        pass

    def has_pending_logs(self, mdn: str) -> bool:
        """
        미전송 로그가 있는지 확인

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            bool: 미전송 로그 존재 여부
        """
        with self.queue_lock:
            return mdn in self.pending_logs and not self.pending_logs[mdn].empty()

    def count_pending_logs(self, mdn: str) -> int:
        """
        미전송 로그 개수 확인

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            int: 미전송 로그 개수
        """
        with self.queue_lock:
            if mdn not in self.pending_logs:
                return 0
            return self.pending_logs[mdn].qsize()

    def store_log(self, mdn: str, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> bool:
        """
        로그 데이터를 저장하고 즉시 전송 시도

        Args:
            mdn: 차량 번호(MDN)
            log_data: 저장할 로그 데이터

        Returns:
            bool: 저장 성공 여부
        """
        # Freeze event data and the actual first-send identity together. Never re-read a new key after failure.
        log_data = log_data.model_copy(deep=True)
        credential = None
        pause_reason = None
        print(f"[INFO] {self.log_type} 로그 즉시 전송 시도 - MDN: {mdn}")
        try:
            if mdn != log_data.mdn:
                pause_reason = "packet_identity_changed"
                raise ValueError("Packet identity mismatch; review required")
            credential = load_device_credential(mdn, self.backend_url)
        except ValueError as error:
            pause_reason = pause_reason or "source_identity_unknown"
            success, error_msg = False, str(error)
        else:
            success, error_msg = self._send_with_credential(log_data, credential)

        if success:
            print(f"[SUCCESS] {self.log_type} 로그 즉시 전송 성공 - MDN: {mdn}")
            return True
        else:
            print(f"[WARNING] {self.log_type} 로그 즉시 전송 실패 - MDN: {mdn}, 오류: {error_msg}")
            print(f"[INFO] 실패한 로그를 대기열에 저장합니다 - MDN: {mdn}")

            # 전송 실패 시 큐에 저장
            with self.queue_lock:
                if mdn not in self.pending_logs:
                    self.pending_logs[mdn] = queue.Queue()

                log_entry = {
                    "data": log_data,
                    "timestamp": datetime.now(),
                    "retry_count": 0,
                    "log_type": self.log_type,
                    "source_binding": credential.binding if credential is not None else None,
                    "retry_state": "paused" if pause_reason else "pending",
                    "pause_reason": pause_reason,
                }

                self.pending_logs[mdn].put(log_entry)
                if pause_reason:
                    print(f"[WARNING] {self.log_type} 자동 재전송 일시 중지 - MDN: {mdn}, 검토 사유: {pause_reason}")
                print(f"[DEBUG] {self.log_type} 로그 저장 성공 - MDN: {mdn}")
                print(f"[INFO] 현재 백엔드 전송 대기 로그 개수: {self.pending_logs[mdn].qsize()} - MDN: {mdn}")
                return True  # 저장은 성공했으므로 True 반환

    def send_log_to_backend(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> Tuple[bool, str]:
        try:
            credential = load_device_credential(log_data.mdn, self.backend_url)
        except ValueError as error:
            return False, str(error)  # Fixed messages only; never echo file contents or credentials.
        return self._send_with_credential(log_data, credential)

    def _send_with_credential(self, log_data, credential) -> Tuple[bool, str]:
        import requests

        # Use the same snapshot that was compared with the queue binding; no credential-file TOCTOU reload.
        headers = credential.headers()
        headers.update({"Content-Type": "application/json", "Accept": "application/json"})
        try:
            response = requests.post(
                f"{self.backend_url.rstrip('/')}{self.backend_endpoint}",
                json=log_data.model_dump(), headers=headers, timeout=10, allow_redirects=False)
            if response.status_code == 401:
                return False, "Device authentication rejected; check binding or replace credential"
            if response.status_code not in (200, 201):
                return False, f"Backend HTTP {response.status_code}"
            result = response.json()
            if isinstance(result, dict) and (result.get("code") == "000" or result.get("rstCd") == "000"):
                return True, "Success"
            return False, "Backend rejected telemetry"
        except requests.exceptions.RequestException:
            return False, "Backend request failed"
        except ValueError:
            return False, "Invalid backend response"

    def process_all_pending_logs(self) -> int:
        """
        모든 MDN에 대한 미전송 로그 처리

        Returns:
            int: 총 처리된 로그 수
        """
        total_processed = 0

        # 현재 큐에 있는 모든 MDN 목록 복사
        with self.queue_lock:
            mdn_list = list(self.pending_logs.keys())

        # 각 MDN에 대한 로그 처리
        for mdn in mdn_list:
            processed = self.process_pending_logs(mdn)
            total_processed += processed

        return total_processed

    def get_pending_logs(self, mdn: str) -> list:
        """
        특정 MDN에 대한 미전송 로그 목록 조회

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            list: 미전송 로그 목록
        """
        logs = []
        with self.queue_lock:
            if mdn in self.pending_logs:
                # 큐의 내용을 리스트로 변환 (큐를 비우지 않고 복사)
                temp_queue = queue.Queue()
                while not self.pending_logs[mdn].empty():
                    log_entry = self.pending_logs[mdn].get()
                    # Callers can inspect status without mutating retained identity or event data.
                    visible = dict(log_entry)
                    visible["data"] = log_entry["data"].model_copy(deep=True)
                    logs.append(visible)
                    temp_queue.put(log_entry)

                # 원래 큐 복원
                self.pending_logs[mdn] = temp_queue

        return logs

    def process_pending_logs(self, mdn: str) -> int:
        """
        특정 MDN에 대한 미전송 로그 처리

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            int: 처리된 로그 수
        """
        processed_count = 0

        with self.queue_lock:
            if mdn not in self.pending_logs or self.pending_logs[mdn].empty():
                return 0

            # 큐에서 항목을 하나씩 처리
            temp_queue = queue.Queue()
            current_time = datetime.now()

            while not self.pending_logs[mdn].empty():
                log_entry = self.pending_logs[mdn].get()
                retry_count = log_entry.get("retry_count", 0)

                # Review-paused rows are retained even past normal retry expiry. Never auto-resume them.
                if log_entry.get("retry_state") == "paused":
                    temp_queue.put(log_entry)
                    continue

                binding = log_entry.get("source_binding")
                pause_reason = None
                credential = None
                if not isinstance(binding, CredentialBinding):
                    pause_reason = "source_identity_unknown"  # Legacy/initially unauthenticated backlog.
                elif mdn != log_entry["data"].mdn or mdn != binding.mdn:
                    pause_reason = "packet_identity_changed"
                else:
                    try:
                        credential = load_device_credential(mdn, self.backend_url)
                    except ValueError:
                        pause_reason = "credential_unavailable"
                    else:
                        if credential.binding != binding:
                            pause_reason = "credential_changed"

                if pause_reason:
                    log_entry["retry_state"] = "paused"
                    log_entry["pause_reason"] = pause_reason
                    temp_queue.put(log_entry)
                    print(f"[WARNING] {self.log_type} 자동 재전송 일시 중지 - MDN: {mdn}, 검토 사유: {pause_reason}")
                    continue

                print(f"[DEBUG] {self.log_type} 로그 처리 시도 - MDN: {mdn}, 재시도: {retry_count}")

                # 오래된 로그는 삭제
                time_diff = current_time - log_entry["timestamp"]
                if time_diff >= timedelta(hours=self.max_storage_hours):
                    print(f"[INFO] {self.log_type} 로그 최대 보관 시간 초과 - 폐기합니다. MDN: {mdn}")
                    continue

                # 로그 전송 시도
                success, error_msg = self._send_with_credential(log_entry["data"], credential)
                processed_count += 1

                if success:
                    print(f"[INFO] {self.log_type} 로그 전송 성공 - MDN: {mdn}")
                    print(f"[DEBUG] 성공한 로그는 더 이상 보관하지 않습니다 (자동 삭제) - MDN: {mdn}")
                else:
                    print(f"[ERROR] {self.log_type} 로그 전송 실패 - MDN: {mdn}, 오류: {error_msg}")
                    # 재시도 횟수 증가
                    log_entry["retry_count"] = retry_count + 1
                    # 전송 실패한 로그는 다시 큐에 넣기
                    print(f"[DEBUG] 실패한 로그 재시도 대기열에 등록 - MDN: {mdn}, 재시도: {log_entry['retry_count']}")
                    temp_queue.put(log_entry)

            # 전송 실패한 로그만 다시 저장
            if not temp_queue.empty():
                self.pending_logs[mdn] = temp_queue
            else:
                del self.pending_logs[mdn]

        return processed_count

    @abc.abstractmethod
    def _print_debug_log(self, log_data: Union[GpsLogRequest, PowerLogRequest, GeofenceLogRequest]) -> None:
        """로그 타입에 맞는 디버그 정보 출력 (추상 메서드)"""
        pass
