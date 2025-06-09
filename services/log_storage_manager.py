import queue
import threading
import requests
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from models.emulator_data import GpsLogRequest, LogResponse

class LogStorageManager:
    """미전송 로그 데이터 저장, 관리 및 전송 담당 클래스"""
    
    def __init__(self, max_storage_hours: int = 1, send_interval_seconds: int = 10):
        # 전송되지 못한 로그를 저장하기 위한 큐 (MDN별)
        self.pending_logs = {}
        # 큐 액세스를 위한 락
        self.queue_lock = threading.Lock()
        # 최대 저장 시간 (기본 1시간)
        self.max_storage_hours = max_storage_hours
        # 로그 전송 간격 (초 단위)
        self.send_interval_seconds = send_interval_seconds
        # 백엔드 API 서버 URL (환경처러는 환경변수나 설정파일에서 가져와야 함)
        self.backend_url = "http://localhost:8080"  # 실제 또는 테스트용 주소로 변경 필요
        # 백엔드 연결 상태 로깅
        self.last_connection_attempt = None
        self.backend_connection_status = "Unknown"
        
        # 백엔드 인증 정보 (실제 운영 시에는 환경변수나 설정파일에서 가져와야 함)
        self.use_auth = False  # 인증 사용 여부
        self.auth_username = "thisway"  # 필요 시 변경
        self.auth_password = "thisway123"  # 필요 시 변경
        
        # 백그라운드 스레드 상태
        self.running = False
        self.sender_thread = None
        
    def store_unsent_log(self, mdn: str, log_data: GpsLogRequest) -> bool:
        """
        미전송 로그 데이터 저장 (최대 1시간)
        
        Args:
            mdn: 차량 번호 (단말기 번호)
            log_data: 저장할 로그 데이터
        """
        try:
            with self.queue_lock:
                # 해당 MDN의 큐가 없으면 생성
                if mdn not in self.pending_logs:
                    self.pending_logs[mdn] = queue.Queue()
                
                # 로그 데이터와 타임스탬프 저장
                log_entry = {
                    "timestamp": datetime.now(),
                    "data": log_data
                }
                
                # 큐에 추가
                self.pending_logs[mdn].put(log_entry)
                
                return True
        except Exception as e:
            print(f"Error storing unsent log: {e}")
            return False
    
    def get_unsent_logs(self, mdn: str) -> List[GpsLogRequest]:
        """
        미전송 로그 데이터 가져오기
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        # 해당 MDN에 저장된 로그가 없으면 빈 리스트 반환
        if mdn not in self.pending_logs:
            return []
        
        unsent_logs = []
        
        with self.queue_lock:
            # 큐에서 꼭 접근하지 않고 임시 리스트에 복사
            temp_queue = queue.Queue()
            current_time = datetime.now()
            
            while not self.pending_logs[mdn].empty():
                log_entry = self.pending_logs[mdn].get()
                
                # 오래된 로그는 삭제 (기본 1시간)
                time_diff = current_time - log_entry["timestamp"]
                if time_diff < timedelta(hours=self.max_storage_hours):
                    # 임시 리스트에 다시 넣어서 유지
                    temp_queue.put(log_entry)
                    # 결과 리스트에 데이터만 추가
                    unsent_logs.append(log_entry["data"])
            
            # 임시 큐에 있는 항목을 다시 원래 큐로 이동
            self.pending_logs[mdn] = temp_queue
        
        return unsent_logs
    
    def send_log_to_backend(self, log_data: GpsLogRequest) -> Tuple[bool, str]:
        """
        로그 데이터를 백엔드 서버로 전송
        
        Args:
            log_data: 전송할 로그 데이터
            
        Returns:
            (성공 여부, 오류 메시지)
        """
        # 로그 유형 확인
        if not log_data:
            return False, "로그 데이터가 비어 있습니다."
            
        # 접근할 엔드포인트 결정
        endpoint = f"{self.backend_url}/api/logs/gps"  # GPS 로그 기본
        
        # 요청 헤더 설정
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            # 로그 데이터를 JSON으로 변환
            log_json = log_data.dict()
            
            # 디버깅용 GPS 좌표 정보 출력
            if log_data.cList and len(log_data.cList) > 0:
                first_item = log_data.cList[0]
                last_item = log_data.cList[-1]
                print(f"[디버깅] GPS 좌표 정보: 처음({first_item.lat}, {first_item.lon}), 마지막({last_item.lat}, {last_item.lon})")
            
            # 연결 시도 상태 업데이트
            self.last_connection_attempt = datetime.now()
            
            # 인증 정보
            auth = None
            if self.use_auth:
                auth = (self.auth_username, self.auth_password)
                print(f"백엔드 요청에 인증 정보 사용")
            
            # Basic 인증 정보와 함께 요청 전송
            print(f"[백엔드 통신] 요청: {endpoint}")  # 요청 정보 출력
            response = requests.post(
                endpoint, 
                json=log_json, 
                headers=headers, 
                auth=auth,
                timeout=10
            )
            
            # 응답 처리
            if response.status_code == 200:
                self.backend_connection_status = "Connected"
                result = response.json()
                if result.get("code") == "000":
                    print(f"[성공] MDN: {log_data.mdn}의 로그가 성공적으로 전송되었습니다.")
                    return True, ""
                else:
                    error_msg = f"백엔드 오류: {result.get('message', '알 수 없는 오류')} (Code: {result.get('code', 'N/A')})"
                    print(f"[오류] {error_msg}")
                    return False, error_msg
            else:
                self.backend_connection_status = f"Error ({response.status_code})"
                error_msg = f"HTTP 오류: {response.status_code} - {response.text}"
                print(f"[오류] {error_msg}")
                return False, error_msg
                
        except requests.ConnectionError as e:
            self.backend_connection_status = "Connection Failed"
            error_msg = f"백엔드 서버 연결 실패: {str(e)} - 백엔드 서버가 실행 중인지 확인해주세요."
            print(f"[오류] {error_msg}")
            return False, error_msg
        except requests.RequestException as e:
            self.backend_connection_status = "Request Failed"
            error_msg = f"요청 실패: {str(e)}"
            print(f"[오류] {error_msg}")
            return False, error_msg
        except Exception as e:
            self.backend_connection_status = "Error"
            error_msg = f"예상치 못한 오류: {str(e)}"
            print(f"[오류] {error_msg}")
            return False, error_msg
    
    def process_pending_logs(self):
        """
        모든 MDN에 대해 미전송 로그 처리 및 전송
        """
        mdns_to_process = list(self.pending_logs.keys())
        
        for mdn in mdns_to_process:
            with self.queue_lock:
                if mdn not in self.pending_logs or self.pending_logs[mdn].empty():
                    continue
                
                # 큐에서 항목을 하나씩 꼭 가져오기
                temp_queue = queue.Queue()
                current_time = datetime.now()
                
                while not self.pending_logs[mdn].empty():
                    log_entry = self.pending_logs[mdn].get()
                    
                    # 오래된 로그는 삭제
                    time_diff = current_time - log_entry["timestamp"]
                    if time_diff >= timedelta(hours=self.max_storage_hours):
                        continue
                    
                    # 로그 전송 시도
                    success, _ = self.send_log_to_backend(log_entry["data"])
                    
                    # 전송 실패한 로그는 다시 큐에 넣기
                    if not success:
                        temp_queue.put(log_entry)
                
                # 전송 실패한 로그만 다시 저장
                self.pending_logs[mdn] = temp_queue
    
    def start_sender_thread(self):
        """
        로그 전송 백그라운드 스레드 시작
        """
        if self.sender_thread is not None and self.sender_thread.is_alive():
            print("Log sender thread is already running")
            return
        
        self.running = True
        self.sender_thread = threading.Thread(target=self._sender_worker, daemon=True)
        self.sender_thread.start()
        print("Log sender thread started")
    
    def stop_sender_thread(self):
        """
        로그 전송 백그라운드 스레드 중지
        """
        self.running = False
        if self.sender_thread is not None:
            self.sender_thread.join(timeout=5.0)
            print("Log sender thread stopped")
    
    def _sender_worker(self):
        """
        백그라운드 스레드 작업 - 주기적으로 로그 전송
        """
        while self.running:
            try:
                self.process_pending_logs()
            except Exception as e:
                print(f"Error in sender worker: {str(e)}")
            
            # 일정 시간 대기
            time.sleep(self.send_interval_seconds)
    
    def clear_unsent_logs(self, mdn: str) -> bool:
        """
        미전송 로그 데이터 삭제
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn in self.pending_logs:
            with self.queue_lock:
                self.pending_logs[mdn] = queue.Queue()
            return True
        return False
    
    def has_pending_logs(self, mdn: str) -> bool:
        """
        미전송 로그가 있는지 확인
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn not in self.pending_logs:
            return False
            
        with self.queue_lock:
            return not self.pending_logs[mdn].empty()
    
    def count_pending_logs(self, mdn: str) -> int:
        """
        미전송 로그 개수 확인
        
        Args:
            mdn: 차량 번호 (단말기 번호)
        """
        if mdn not in self.pending_logs:
            return 0
            
        with self.queue_lock:
            # 임시 저장소
            temp_queue = queue.Queue()
            count = 0
            
            # 큐에서 모든 항목을 꺼내어 처리
            while not self.pending_logs[mdn].empty():
                item = self.pending_logs[mdn].get()
                temp_queue.put(item)
                count += 1
            
            # 원래 큐를 임시 큐로 교체
            self.pending_logs[mdn] = temp_queue
            
            return count
