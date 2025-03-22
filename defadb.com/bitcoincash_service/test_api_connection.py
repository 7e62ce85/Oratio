#!/usr/bin/env python3
# test_api_connection.py - API 연결 테스트

import requests
import time
import sys

# 테스트할 API 엔드포인트들
apis = [
    "https://api.blockchair.com/bitcoin-cash/dashboards/address/qr3jejs0qn6wnssw8659duv7c3nnx92f6sfsvam05w",
    "https://rest.bitcoin.com/v2/address/details/qr3jejs0qn6wnssw8659duv7c3nnx92f6sfsvam05w",
    "https://bch-chain.api.btc.com/v3/address/qr3jejs0qn6wnssw8659duv7c3nnx92f6sfsvam05w"
]

# 각 API 테스트
print("API 연결 테스트 시작...\n")

for api_url in apis:
    print(f"테스트: {api_url}")
    try:
        start_time = time.time()
        response = requests.get(api_url, timeout=5)
        elapsed = time.time() - start_time
        
        print(f"  상태: {'성공' if response.status_code == 200 else '실패'}")
        print(f"  코드: {response.status_code}")
        print(f"  응답 시간: {elapsed:.2f}초")
        
        if response.status_code == 200:
            try:
                data = response.json()
                # 첫 30자만 표시 (가독성을 위해)
                data_preview = str(data)[:100] + "..." if len(str(data)) > 100 else str(data)
                print(f"  응답 데이터: {data_preview}")
            except Exception as e:
                print(f"  JSON 파싱 오류: {str(e)}")
    except requests.exceptions.RequestException as e:
        print(f"  연결 오류: {str(e)}")
    
    print("")  # 줄바꿈

print("테스트 완료")