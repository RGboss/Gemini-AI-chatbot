import requests
import json
import time

WORKER_IP = "192.168.29.94"
BASE_URL = f"http://{WORKER_IP}:8081"

def test_endpoints():
    print(f"Testing Gemini-AI-chatbot on {BASE_URL}...")
    
    # 1. Health check via Nginx
    try:
        health_resp = requests.get(f"{BASE_URL}/health", timeout=10)
        print(f"GET /health status: {health_resp.status_code}")
        print(f"GET /health body: {health_resp.text}")
    except Exception as e:
        print(f"GET /health failed: {e}")

    # 2. Frontend HTML check
    try:
        fe_resp = requests.get(f"{BASE_URL}/", timeout=10)
        print(f"GET / status: {fe_resp.status_code}")
        print(f"GET / preview: {fe_resp.text[:200]}...")
    except Exception as e:
        print(f"GET / failed: {e}")

    # 3. Test API Chat query
    try:
        chat_payload = {
            "message": "Hello! Reply with exactly: 'Worker Redmi Note 5 Pro is online and ready!'"
        }
        print("Sending POST /api/chat...")
        t0 = time.time()
        chat_resp = requests.post(f"{BASE_URL}/api/chat", json=chat_payload, timeout=60)
        elapsed = time.time() - t0
        print(f"POST /api/chat status: {chat_resp.status_code} in {elapsed:.2f}s")
        print(f"POST /api/chat response: {chat_resp.text}")
    except Exception as e:
        print(f"POST /api/chat failed: {e}")

if __name__ == "__main__":
    test_endpoints()
