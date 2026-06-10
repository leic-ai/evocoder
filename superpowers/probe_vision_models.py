"""探测支持图片输入的模型"""
import requests
import base64
import io
import zlib
import struct

API_KEY = "sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g"
BASE_URL = "https://api.xiaomimimo.com/v1"

# 创建1x1红色PNG
sig = b'\x89PNG\r\n\x1a\n'
ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
raw = b'\x00\xff\x00\x00'
compressed = zlib.compress(raw)

def make_chunk(ctype, data):
    c = ctype + data
    crc = struct.pack('>I', 0)
    return struct.pack('>I', len(data)) + c + crc

png = sig + make_chunk(b'IHDR', ihdr_data) + make_chunk(b'IDAT', compressed) + make_chunk(b'IEND', b'')
b64 = base64.b64encode(png).decode()
img_url = f"data:image/png;base64,{b64}"

models = [
    "mimo-v2.5",
    "mimo-v2.5-pro", 
    "mimo-v2.5-vision",
    "mimo-v2.5-pro-vision",
    "mimo-vl",
    "MiMo-VL",
    "mimo-multimodal",
    "MiMo-VL-7B",
]

headers = {"api-key": API_KEY, "Content-Type": "application/json"}

for m in models:
    body = {
        "model": m,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "What color? Reply one word."},
                {"type": "image_url", "image_url": {"url": img_url}}
            ]
        }],
        "max_tokens": 10
    }
    try:
        r = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=30)
        if r.status_code == 200:
            data = r.json()
            content = data["choices"][0]["message"].get("content", "")
            print(f"  ✅ {m}: {content[:50]}")
        else:
            err = ""
            try:
                err = r.json().get("error", {}).get("message", r.text[:80])
            except:
                err = r.text[:80]
            print(f"  ❌ {m} (HTTP {r.status_code}): {str(err)[:80]}")
    except Exception as e:
        print(f"  ❌ {m}: {e}")
