import requests
import sys

def test_api(url):
    try:
        print(f"Testing connection to: {url}")
        response = requests.get(url, timeout=10)
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text[:200]}...")
        return True
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    apis = [
        "https://api.blockchair.com/bitcoin-cash/stats",
        "https://bch-chain.api.btc.com/v3/block/latest",
        "https://rest.bitcoin.com/v2/blockchain/info"  
    ]
    
    for api in apis:
        success = test_api(api)
        print(f"Result: {'Success' if success else 'Failed'}")
        print("-" * 50)