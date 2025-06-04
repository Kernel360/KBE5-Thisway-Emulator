import os
from dotenv import load_dotenv

# .env 파일이 있으면 로드
load_dotenv()

# 기본 설정
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', '8081'))
DEBUG_MODE = os.getenv('DEBUG_MODE', 'True').lower() in ('true', '1', 't')

# 위치 기본 설정 (한국 중심)
DEFAULT_LATITUDE = float(os.getenv('DEFAULT_LATITUDE', '37.5665'))
DEFAULT_LONGITUDE = float(os.getenv('DEFAULT_LONGITUDE', '126.9780'))
