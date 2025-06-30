"""
GPS 로그 생성기
GPS 관련 로그 데이터를 생성하는 클래스
"""

import random
import os
import requests
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from models.emulator_data import GpsLogRequest, GpsLogItem
from services.log_generators.base_log_generator import BaseLogGenerator

class GpsLogGenerator(BaseLogGenerator):
    """GPS 로그 데이터 생성 담당 클래스"""

    def generate_gps_log(self, mdn: str, generate_full: bool = True) -> Optional[GpsLogRequest]:
        """
        GPS 로그 요청 데이터 생성 (0~59초 데이터)
        카카오 모빌리티 API만 사용하여 GPS 데이터 생성

        Args:
            mdn: 차량 번호 (단말기 번호)
            generate_full: True면 60개의 전체 데이터 생성, False면 스냅샷용 1개만 생성

        Returns:
            GpsLogRequest: GPS 로그 요청 객체
        """
        # 에뮬레이터가 없거나 활성화되지 않은 경우
        emulator = self.get_emulator(mdn)
        if not emulator:
            return None

        # 설정 파일에서 카카오 API 사용 여부 및 기본 경로 정보 가져오기
        try:
            import json
            with open('config.json', 'r') as f:
                config = json.load(f)
                use_kakao_api = config.get("use_kakao_api", False)
                default_route = config.get("default_route", {})
        except Exception as e:
            print(f"설정 파일 로드 중 오류 발생: {e}")
            print("카카오 API 설정이 필요합니다. config.json 파일을 확인해주세요.")
            return None

        # 카카오 API 설정 확인
        if not use_kakao_api:
            print("카카오 API 사용이 비활성화되어 있습니다. config.json 파일에서 use_kakao_api를 true로 설정해주세요.")
            return None

        # 경로 정보 확인
        if "start_point" not in default_route or "end_point" not in default_route:
            print("경로 정보가 설정되지 않았습니다. config.json 파일에서 default_route 설정을 확인해주세요.")
            return None

        # 카카오 API를 사용하여 GPS 로그 생성
        start_point = tuple(default_route["start_point"])
        end_point = tuple(default_route["end_point"])

        kakao_gps_log = self.generate_gps_log_from_kakao_route(
            mdn=mdn,
            start_point=start_point,
            end_point=end_point,
            generate_full=generate_full
        )

        # 카카오 API 호출이 실패한 경우
        if not kakao_gps_log:
            print("카카오 API를 사용한 GPS 로그 생성에 실패했습니다.")
            return None

        return kakao_gps_log

    def process_received_gps_log(self, log_data: GpsLogRequest) -> bool:
        """
        수신된 GPS 로그 데이터 처리

        Args:
            log_data: GPS 로그 요청 데이터
        """
        # 로그 처리 로직 (향후 구현)
        return True

    def create_gps_log_from_collected_data(self, mdn: str, collected_data: List[Dict]) -> GpsLogRequest:
        """
        실시간으로 수집된 GPS 데이터를 구조화된 로그로 변환

        Args:
            mdn: 차량 번호
            collected_data: 실시간으로 수집된 데이터 목록
        """
        if not mdn or not collected_data:
            return None

        emulator = self.get_emulator(mdn)
        if not emulator:
            return None

        current_time = datetime.now()
        time_str = current_time.strftime("%Y%m%d%H%M%S")

        # 디버깅 정보 출력
        print(f"[DEBUG] 수집된 데이터 첫 항목 키: {list(collected_data[0].keys()) if collected_data else 'None'}")

        # 누적 거리 계산을 위한 변수
        total_distance = self.emulator_manager.get_accumulated_distance(mdn)

        log_items = []
        for i, data in enumerate(collected_data):
            # 이전 데이터 포인트와의 거리 계산 및 누적
            distance = 0
            angle = data.get("angle", 0)  # 기본값 사용
            speed = data.get("speed", 0)  # 기본값 사용

            if i > 0:
                prev_data = collected_data[i-1]
                prev_lat = prev_data.get("latitude", 0)
                prev_lon = prev_data.get("longitude", 0)
                curr_lat = data.get("latitude", 0)
                curr_lon = data.get("longitude", 0)
                prev_speed = prev_data.get("speed", 0)
                prev_angle = prev_data.get("angle", 0)

                # 거리 계산 (미터 단위)
                distance = self.calculate_distance(prev_lat, prev_lon, curr_lat, curr_lon)

                # 시간 간격 계산 (초 단위)
                prev_time = prev_data.get("timestamp")
                curr_time = data.get("timestamp")
                time_diff = 1.0  # 기본값 1초

                if prev_time and curr_time:
                    time_diff = (curr_time - prev_time).total_seconds()
                    if time_diff <= 0:
                        time_diff = 1.0  # 시간 차이가 없거나 음수인 경우 기본값 사용

                # 속도 계산 (km/h) - 거리(m) / 시간(초) * 3.6
                if distance > 0 and time_diff > 0:
                    current_speed = (distance / time_diff) * 3.6
                    # 급격한 속도 변화 방지를 위한 스무딩 (이전 속도의 70%, 현재 속도의 30%)
                    speed = prev_speed * 0.7 + current_speed * 0.3
                else:
                    speed = prev_speed * 0.9  # 이동이 없으면 감속

                # 속도 제한 (0~120 km/h)
                speed = max(0, min(120, speed))

                # 방향각 계산 (두 좌표 사이의 방위각)
                if distance > 0:
                    import math
                    # 위도/경도를 라디안으로 변환
                    lat1_rad = math.radians(prev_lat)
                    lon1_rad = math.radians(prev_lon)
                    lat2_rad = math.radians(curr_lat)
                    lon2_rad = math.radians(curr_lon)

                    # 방위각 계산 (북쪽이 0도, 시계 방향)
                    y = math.sin(lon2_rad - lon1_rad) * math.cos(lat2_rad)
                    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon2_rad - lon1_rad)
                    angle_rad = math.atan2(y, x)
                    current_angle = (math.degrees(angle_rad) + 360) % 360

                    # 급격한 방향 변화 방지를 위한 스무딩 (이전 방향의 80%, 현재 방향의 20%)
                    # 단, 방향 차이가 180도 이상이면 스무딩 없이 새 방향 사용
                    angle_diff = abs(current_angle - prev_angle)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff

                    if angle_diff < 180:
                        angle = prev_angle * 0.8 + current_angle * 0.2
                    else:
                        angle = current_angle
                else:
                    angle = prev_angle  # 이동이 없으면 이전 방향 유지

                # 누적 거리 업데이트 (80m 이상 이동은 비정상으로 간주하고 제외)
                if distance <= 80:
                    total_distance += distance

            # 위도/경도 값을 소수점 6자리로 제한하고 1,000,000 곱하기
            lat_value = round(data.get("latitude", 0), 6)
            lon_value = round(data.get("longitude", 0), 6)

            # 타임스탬프에서 분, 초 정보 추출
            timestamp = data.get("timestamp")
            minutes = timestamp.minute if timestamp else 0
            seconds = timestamp.second if timestamp else i

            log_item = GpsLogItem(
                min=str(minutes),
                sec=str(seconds),
                gcd="A",  # 기본값 A (정상)
                lat=str(int(lat_value * 1000000)),  # 소수점 6자리로 제한하고 1,000,000 곱하기
                lon=str(int(lon_value * 1000000)),  # 소수점 6자리로 제한하고 1,000,000 곱하기
                ang=str(int(angle)),  # 계산된 방향각 사용
                spd=str(int(speed)),  # 계산된 속도 사용
                sum=str(int(total_distance)),  # 계산된 누적 거리 사용
                bat=str(int(data.get("battery", 0)))  # battery 키 사용
            )
            log_items.append(log_item)

        # 최종 누적 거리를 에뮬레이터 매니저에 업데이트
        self.emulator_manager.update_accumulated_distance(int(total_distance), mdn)

        gps_log = GpsLogRequest(
            mdn=mdn,
            tid="A001",
            mid="6",
            pv="5",
            did="1",
            oTime=time_str,
            cCnt=str(len(log_items)),
            cList=log_items
        )

        return gps_log

    def generate_gps_log_from_kakao_route(self, mdn: str, start_point: Tuple[float, float], 
                                         end_point: Tuple[float, float], 
                                         generate_full: bool = True) -> Optional[GpsLogRequest]:
        """
        카카오모빌리티 API를 사용하여 출발지와 목적지 사이의 경로를 기반으로 GPS 로그 생성

        Args:
            mdn: 차량 번호 (단말기 번호)
            start_point: 출발 지점의 (위도, 경도)
            end_point: 도착 지점의 (위도, 경도)
            generate_full: True면 60개의 전체 데이터 생성, False면 스냅샷용 1개만 생성

        Returns:
            GpsLogRequest: GPS 로그 요청 객체
        """
        print(f"[DEBUG] 카카오 API 경로 생성 시작 - MDN: {mdn}, 출발: {start_point}, 도착: {end_point}")

        # 1. 카카오모빌리티 API 호출하여 경로 데이터 가져오기
        print(f"[DEBUG] 카카오 API 호출 시작 - 출발: {start_point}, 도착: {end_point}")
        route_data = self._get_kakao_route(start_point, end_point)
        print(f"[DEBUG] 카카오 API 호출 결과: {'성공' if route_data else '실패'}")

        if not route_data:
            print(f"[ERROR] 카카오 API에서 경로 데이터를 가져오지 못했습니다 - MDN: {mdn}")
            return None

        # 2. 경로 데이터를 적절한 간격으로 분할
        print(f"[DEBUG] 경로 데이터 분할 시작")
        route_points = self._extract_route_points(route_data, generate_full)
        print(f"[DEBUG] 경로 데이터 분할 완료: {len(route_points)}개 포인트")

        if not route_points or len(route_points) == 0:
            print(f"[ERROR] 경로 포인트 추출 실패 - 추출된 포인트 없음 - MDN: {mdn}")
            return None

        # 3. 에뮬레이터 매니저에 경로 데이터 설정
        emulator = self.get_emulator(mdn)
        if emulator and hasattr(self.emulator_manager, 'set_kakao_route_data'):
            print(f"[DEBUG] 에뮬레이터 매니저에 경로 데이터 설정 시작: {len(route_points)}개 포인트")
            success = self.emulator_manager.set_kakao_route_data(route_points)
            print(f"[DEBUG] 에뮬레이터 매니저에 카카오 API 경로 데이터 설정 {'성공' if success else '실패'}: {len(route_points)}개 포인트")
        else:
            print(f"[WARNING] 에뮬레이터가 없거나 set_kakao_route_data 메서드가 없습니다 - MDN: {mdn}")

        # 4. 분할된 경로 데이터를 수집된 데이터 형식으로 변환
        print(f"[DEBUG] 경로 데이터를 수집 데이터 형식으로 변환 시작")
        collected_data = self._convert_route_to_collected_data(route_points)
        print(f"[DEBUG] 경로 데이터 변환 완료: {len(collected_data)}개 데이터 포인트")

        # 5. 기존 create_gps_log_from_collected_data 메서드 활용하여 GPS 로그 생성
        print(f"[DEBUG] GPS 로그 생성 시작 - MDN: {mdn}")
        result = self.create_gps_log_from_collected_data(mdn, collected_data)
        print(f"[DEBUG] GPS 로그 생성 {'성공' if result else '실패'} - MDN: {mdn}")

        return result

    def _get_kakao_route(self, start: Tuple[float, float], end: Tuple[float, float]) -> Dict:
        """카카오모빌리티 API를 호출하여 경로 데이터 가져오기"""
        import json
        from urllib.parse import urlencode

        # API 키는 환경 변수나 설정 파일에서 가져오는 것이 좋습니다
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                api_key = config.get("kakao_api_key", "")
        except Exception as e:
            print(f"[ERROR] 설정 파일 로드 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()  # 상세 오류 스택 출력
            return None

        if not api_key or api_key == "YOUR_KAKAO_API_KEY":
            print("[ERROR] 카카오 API 키가 설정되지 않았습니다. config.json 파일에서 설정해주세요.")
            return None

        # API 키 마스킹 (앞 4자리와 뒤 4자리만 표시)
        if len(api_key) > 8:
            masked_key = f"{api_key[:4]}...{api_key[-4:]}"
        else:
            masked_key = "****"  # 키가 너무 짧으면 전체 마스킹
        print(f"[DEBUG] 카카오 API 키: {masked_key}")

        url = "https://apis-navi.kakaomobility.com/v1/directions"
        headers = {
            "Authorization": f"KakaoAK {api_key}",
            "Content-Type": "application/json"
        }

        # 출발지와 목적지 좌표 (경도,위도 순서로 입력)
        origin = f"{start[1]},{start[0]}"
        destination = f"{end[1]},{end[0]}"

        # 디버그 로깅
        print(f"[DEBUG] 카카오 API 요청 - 출발지: {origin}")
        print(f"[DEBUG] 카카오 API 요청 - 목적지: {destination}")

        params = {
            "origin": origin,
            "destination": destination,
            "priority": "RECOMMEND",  # 추천 경로
            "car_fuel": "GASOLINE",
            "car_hipass": False,
            "alternatives": False,
            "road_details": True  # 상세 도로 정보 요청
        }

        # 전체 요청 URL 로깅 (파라미터 포함)
        full_url = f"{url}?{urlencode(params)}"
        print(f"[DEBUG] 카카오 API 전체 요청 URL: {full_url}")
        print(f"[DEBUG] 카카오 API 요청 헤더: {headers}")

        try:
            print("[DEBUG] 카카오 API 호출 시작...")
            response = requests.get(url, headers=headers, params=params)
            print(f"[DEBUG] 카카오 API 응답 상태 코드: {response.status_code}")
            print(f"[DEBUG] 카카오 API 응답 헤더: {response.headers}")

            if response.status_code == 200:
                response_json = response.json()

                # 응답 데이터 구조 로깅 (전체 응답은 너무 클 수 있으므로 주요 키만)
                print(f"[DEBUG] 카카오 API 응답 주요 키: {list(response_json.keys())}")

                if 'routes' in response_json and response_json['routes']:
                    route = response_json['routes'][0]
                    print(f"[DEBUG] 경로 정보 존재: 섹션 수: {len(route.get('sections', []))}")

                    # 첫 번째 섹션의 정보만 로깅
                    if route.get('sections'):
                        first_section = route['sections'][0]
                        print(f"[DEBUG] 첫 번째 섹션 정보: 도로 수: {len(first_section.get('roads', []))}")

                        # 첫 번째 도로의 정보만 로깅
                        if first_section.get('roads'):
                            first_road = first_section['roads'][0]
                            print(f"[DEBUG] 첫 번째 도로 정보: 좌표 수: {len(first_road.get('vertexes', [])) // 2}")
                else:
                    print("[DEBUG] 경로 정보가 없습니다.")
                    print(f"[DEBUG] 전체 응답 내용: {json.dumps(response_json, indent=2, ensure_ascii=False)}")

                return response_json
            else:
                print(f"[ERROR] API 호출 실패: {response.status_code}")
                print(f"[ERROR] 응답 내용: {response.text}")
                return None
        except Exception as e:
            print(f"[ERROR] API 호출 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()  # 상세 오류 스택 출력
            return None

    def _extract_route_points(self, route_data: Dict, generate_full: bool) -> List[Dict]:
        """경로 데이터에서 좌표 추출 및 적절한 간격으로 분할"""
        print(f"[DEBUG] 경로 데이터에서 좌표 추출 시작 - 전체 데이터 생성: {generate_full}")
        route_points = []

        # 경로 데이터 유효성 검사
        if not route_data:
            print(f"[ERROR] 경로 데이터가 없습니다")
            return []

        print(f"[DEBUG] 경로 데이터 키: {list(route_data.keys())}")

        if 'routes' in route_data and route_data['routes']:
            routes = route_data['routes']
            print(f"[DEBUG] 경로 수: {len(routes)}")

            route = routes[0]  # 첫 번째 경로 사용
            print(f"[DEBUG] 첫 번째 경로 키: {list(route.keys())}")

            sections = route.get('sections', [])
            print(f"[DEBUG] 섹션 수: {len(sections)}")

            # 모든 섹션(출발지-경유지1, 경유지1-경유지2, ..., 경유지N-목적지)에서 좌표 추출
            total_roads = 0
            total_vertices = 0

            for section_idx, section in enumerate(sections):
                roads = section.get('roads', [])
                print(f"[DEBUG] 섹션 {section_idx+1}/{len(sections)} - 도로 수: {len(roads)}")
                total_roads += len(roads)

                for road_idx, road in enumerate(roads):
                    vertices = road.get('vertexes', [])
                    vertex_count = len(vertices) // 2  # 좌표는 [경도, 위도] 쌍으로 제공됨
                    total_vertices += vertex_count

                    # 첫 번째 도로와 마지막 도로만 상세 로깅
                    if road_idx == 0 or road_idx == len(roads) - 1:
                        print(f"[DEBUG] 섹션 {section_idx+1} - 도로 {road_idx+1}/{len(roads)} - 좌표 수: {vertex_count}")

                    # 좌표는 [경도, 위도, 경도, 위도, ...] 형식으로 제공됨
                    for i in range(0, len(vertices), 2):
                        if i+1 < len(vertices):
                            lon, lat = vertices[i], vertices[i+1]
                            route_points.append({
                                "longitude": lon,
                                "latitude": lat
                            })

            print(f"[DEBUG] 총 추출된 좌표 수: {len(route_points)} (섹션: {len(sections)}, 도로: {total_roads}, 좌표 쌍: {total_vertices})")

            # 첫 번째와 마지막 좌표 로깅
            if route_points:
                first_point = route_points[0]
                last_point = route_points[-1]
                print(f"[DEBUG] 첫 번째 좌표: ({first_point['latitude']}, {first_point['longitude']})")
                print(f"[DEBUG] 마지막 좌표: ({last_point['latitude']}, {last_point['longitude']})")
        else:
            print(f"[WARNING] 경로 데이터에 'routes' 키가 없거나 비어 있습니다")
            if 'routes' in route_data:
                print(f"[DEBUG] routes 배열 길이: {len(route_data['routes'])}")

        # 경로 포인트 샘플링
        print(f"[DEBUG] 경로 포인트 샘플링 시작 - 추출된 포인트 수: {len(route_points)}")

        if generate_full:
            # 모든 경로 포인트 사용
            if len(route_points) > 60:
                print(f"[DEBUG] 모든 포인트 사용 - 총 포인트 수: {len(route_points)}")
                return route_points
            elif len(route_points) < 60:
                # 포인트가 60개 미만이면 보간하여 60개로 만들기
                print(f"[DEBUG] 60개 포인트로 업샘플링(보간) - 원본 포인트 수: {len(route_points)}")
                interpolated = self._interpolate_points(route_points, 60)
                print(f"[DEBUG] 보간 완료 - 결과 포인트 수: {len(interpolated)}")
                return interpolated
            else:
                print(f"[DEBUG] 포인트 수가 정확히 60개이므로 샘플링 불필요")
                return route_points
        else:
            # 스냅샷용 1개만 필요한 경우
            print(f"[DEBUG] 스냅샷용 첫 번째 포인트만 반환")
            result = [route_points[0]] if route_points else []
            print(f"[DEBUG] 반환할 포인트 수: {len(result)}")
            return result

    def _interpolate_points(self, points: List[Dict], target_count: int) -> List[Dict]:
        """좌표 목록을 target_count 개수로 보간"""
        print(f"[DEBUG] 좌표 보간 시작 - 원본 포인트 수: {len(points)}, 목표 포인트 수: {target_count}")

        if len(points) <= 1:
            print(f"[WARNING] 보간할 포인트가 충분하지 않습니다 (최소 2개 필요) - 현재: {len(points)}개")
            return points

        if target_count <= len(points):
            print(f"[DEBUG] 목표 포인트 수({target_count})가 원본 포인트 수({len(points)})보다 작거나 같아 보간이 필요하지 않습니다")
            return points

        result = []
        # 첫 번째 포인트 추가
        result.append(points[0])
        print(f"[DEBUG] 첫 번째 포인트 추가: ({points[0]['latitude']}, {points[0]['longitude']})")

        # 각 구간별로 필요한 보간 포인트 수 계산
        segments = len(points) - 1
        points_per_segment = (target_count - len(points)) / segments
        print(f"[DEBUG] 보간 계획 - 구간 수: {segments}, 구간당 평균 보간 포인트 수: {points_per_segment:.2f}")

        total_interpolated = 0

        for i in range(segments):
            # 현재 구간에 필요한 보간 포인트 수
            interpolation_count = int(points_per_segment * (i + 1)) - int(points_per_segment * i)
            total_interpolated += interpolation_count

            start_point = points[i]
            end_point = points[i + 1]

            # 구간 정보 로깅 (첫 번째, 마지막, 그리고 10개 구간마다)
            if i == 0 or i == segments - 1 or i % 10 == 0:
                print(f"[DEBUG] 구간 {i+1}/{segments} - 시작: ({start_point['latitude']}, {start_point['longitude']}), " +
                      f"끝: ({end_point['latitude']}, {end_point['longitude']}), 보간 포인트 수: {interpolation_count}")

            # 두 포인트 사이 보간
            for j in range(1, interpolation_count + 1):
                ratio = j / (interpolation_count + 1)
                lat = start_point["latitude"] + (end_point["latitude"] - start_point["latitude"]) * ratio
                lon = start_point["longitude"] + (end_point["longitude"] - start_point["longitude"]) * ratio

                result.append({
                    "latitude": lat,
                    "longitude": lon
                })

                # 첫 번째와 마지막 보간 포인트만 로깅
                if (i == 0 or i == segments - 1) and (j == 1 or j == interpolation_count):
                    print(f"[DEBUG] 보간 포인트 추가 - 구간 {i+1}, 포인트 {j}/{interpolation_count}: ({lat}, {lon})")

            # 구간의 끝 포인트 추가 (마지막 구간 제외)
            if i < segments - 1:
                result.append(end_point)

        # 마지막 포인트 추가
        result.append(points[-1])
        print(f"[DEBUG] 마지막 포인트 추가: ({points[-1]['latitude']}, {points[-1]['longitude']})")

        print(f"[DEBUG] 보간 완료 - 원본 포인트 수: {len(points)}, 보간된 포인트 수: {total_interpolated}, 결과 포인트 수: {len(result)}")

        # 목표 포인트 수와 결과 포인트 수가 다른 경우 경고
        if len(result) != target_count:
            print(f"[WARNING] 보간 결과 포인트 수({len(result)})가 목표 포인트 수({target_count})와 다릅니다")

        return result

    def _convert_route_to_collected_data(self, route_points: List[Dict]) -> List[Dict]:
        """경로 포인트를 수집된 데이터 형식으로 변환"""
        print(f"[DEBUG] 경로 포인트를 수집 데이터 형식으로 변환 시작 - 포인트 수: {len(route_points)}")

        if not route_points:
            print(f"[WARNING] 변환할 경로 포인트가 없습니다")
            return []

        collected_data = []
        base_time = datetime.now()
        print(f"[DEBUG] 기준 시간 설정: {base_time.strftime('%Y-%m-%d %H:%M:%S')}")

        # 첫 번째와 마지막 포인트 로깅
        if len(route_points) > 0:
            first_point = route_points[0]
            last_point = route_points[-1]
            print(f"[DEBUG] 첫 번째 포인트: ({first_point['latitude']}, {first_point['longitude']})")
            print(f"[DEBUG] 마지막 포인트: ({last_point['latitude']}, {last_point['longitude']})")

        for i, point in enumerate(route_points):
            # 각 포인트에 시간 정보 추가 (1초 간격)
            timestamp = base_time + timedelta(seconds=i)

            # 배터리 전압 랜덤 생성 (실제 구현에서는 다른 방식으로 처리 가능)
            battery_voltage = random.uniform(11.5, 14.5) * 10  # 자동차 배터리 일반 전압 범위

            data_point = {
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "timestamp": timestamp,
                "battery": battery_voltage,
                # 속도와 방향각은 create_gps_log_from_collected_data 메서드에서 계산됨
                "speed": 0,
                "angle": 0
            }
            collected_data.append(data_point)

            # 첫 번째, 마지막, 그리고 10개 포인트마다 로깅
            if i == 0 or i == len(route_points) - 1 or i % 10 == 0:
                print(f"[DEBUG] 데이터 포인트 변환 {i+1}/{len(route_points)} - 좌표: ({point['latitude']}, {point['longitude']}), " +
                      f"시간: {timestamp.strftime('%H:%M:%S')}, 배터리: {battery_voltage:.1f}")

        print(f"[DEBUG] 경로 포인트 변환 완료 - 입력: {len(route_points)}개, 출력: {len(collected_data)}개")

        # 입력과 출력 포인트 수가 다른 경우 경고
        if len(collected_data) != len(route_points):
            print(f"[WARNING] 변환된 데이터 포인트 수({len(collected_data)})가 입력 포인트 수({len(route_points)})와 다릅니다")

        return collected_data
