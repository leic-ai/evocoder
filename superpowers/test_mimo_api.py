"""Test MiMo API connection - 修正后的版本"""
import os
import base64
import io
import requests
import json

API_KEY = "sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g"
BASE_URL = "https://api.xiaomimimo.com/v1"
MODEL = "mimo-v2.5-pro"

def test_text():
    """测试纯文本生成"""
    print("[1] Testing text generation...")
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "api-key": API_KEY,
        "Content-Type": "application/json"
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 10
    }
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            print(f"  ✅ Text OK: {content[:100]}")
            return True
        else:
            print(f"  ❌ Error: {resp.text[:300]}")
            # 尝试用 Authorization: Bearer 方式
            print("  尝试 Bearer token 方式...")
            headers2 = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
            resp2 = requests.post(url, headers=headers2, json=body, timeout=30)
            print(f"  Status: {resp2.status_code}")
            if resp2.status_code == 200:
                data = resp2.json()
                content = data["choices"][0]["message"]["content"]
                print(f"  ✅ Text OK (Bearer): {content[:100]}")
                return True
            else:
                print(f"  ❌ Bearer also failed: {resp2.text[:300]}")
            return False
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False

def test_vision():
    """测试视觉（多模态）"""
    print("\n[2] Testing vision (multimodal)...")
    
    # 创建一个简单的测试图片
    try:
        from PIL import Image
        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        img_url = f"data:image/png;base64,{b64}"
    except ImportError:
        # 没有PIL，用一个最小的PNG
        # 1x1 red pixel PNG
        import struct
        def make_tiny_png():
            sig = b'\x89PNG\r\n\x1a\n'
            def chunk(ctype, data):
                c = ctype + data
                crc = struct.pack('>I', 0)  # simplified
                return struct.pack('>I', len(data)) + c + crc
            ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            raw = b'\x00\xff\x00\x00'  # filter byte + RGB
            import zlib
            compressed = zlib.compress(raw)
            return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
        b64 = base64.b64encode(make_tiny_png()).decode()
        img_url = f"data:image/png;base64,{b64}"
    
    url = f"{BASE_URL}/chat/completions"
    headers = {
        "api-key": API_KEY,
        "Content-Type": "application/json"
    }
    body = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is this image? Reply with just the color name."},
                {"type": "image_url", "image_url": {"url": img_url}}
            ]
        }],
        "max_tokens": 20
    }
    
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        print(f"  Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            print(f"  ✅ Vision OK!")
            print(f"  Content: {content[:200]}")
            if reasoning:
                print(f"  Reasoning: {reasoning[:200]}")
            return True
        else:
            print(f"  ❌ Error: {resp.text[:500]}")
            return False
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("MiMo API 测试")
    print(f"Base URL: {BASE_URL}")
    print(f"Model: {MODEL}")
    print("=" * 50)
    
    ok1 = test_text()
    ok2 = False
    if ok1:
        ok2 = test_vision()
    
    print("\n" + "=" * 50)
    print(f"结果: Text={'✅' if ok1 else '❌'}  Vision={'✅' if ok2 else '❌'}")
    print("=" * 50)
