import os
from dotenv import load_dotenv

# .env 파일이 있으면 로드
load_dotenv()

# 위치 기본 설정 (한국 중심)
DEFAULT_LATITUDE = float(os.getenv('DEFAULT_LATITUDE', '37.5665'))
DEFAULT_LONGITUDE = float(os.getenv('DEFAULT_LONGITUDE', '126.9780'))
