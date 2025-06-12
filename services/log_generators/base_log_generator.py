"""
기본 로그 생성기 추상 클래스
모든 로그 타입별 생성기가 상속받는 기본 클래스
"""

from abc import ABC, abstractmethod
import math
from typing import Dict, Any, Optional

from services.emulator_manager import EmulatorManager

class BaseLogGenerator(ABC):
    """로그 생성기의 기본 추상 클래스"""

    def __init__(self, emulator_manager: EmulatorManager):
        """
        로그 생성기 초기화

        Args:
            emulator_manager: 에뮬레이터 관리자 인스턴스
        """
        self.emulator_manager = emulator_manager

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        두 지점 간의 거리를 미터 단위로 계산 (Haversine 공식)

        Args:
            lat1: 시작 위도
            lon1: 시작 경도
            lat2: 종료 위도
            lon2: 종료 경도

        Returns:
            float: 거리(미터)
        """
        R = 6371000  # 지구 반경 (미터)
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        return distance

    def is_emulator_active(self, mdn: str) -> bool:
        """
        에뮬레이터 활성화 상태 확인

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            bool: 에뮬레이터 활성화 여부
        """
        return self.emulator_manager.is_emulator_active(mdn)

    def get_emulator(self, mdn: str) -> Optional[Dict[str, Any]]:
        """
        에뮬레이터 객체 조회

        Args:
            mdn: 차량 번호(MDN)

        Returns:
            Optional[Dict[str, Any]]: 에뮬레이터 객체
        """
        if not self.is_emulator_active(mdn):
            return None
        # 단일 에뮬레이터 모드에서는 active_emulators에서 가져옴
        if mdn in self.emulator_manager.active_emulators:
            return self.emulator_manager.active_emulators[mdn]
        # 호환성을 위해 에뮬레이터 딕셔너리 생성
        return self.emulator_manager.get_emulator_dict()
