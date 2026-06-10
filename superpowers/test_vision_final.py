"""测试 mimo-v2.5 视觉能力 - 用正常尺寸图片"""
import requests
import base64
import io
from PIL import Image

API_KEY = "sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g"
BASE_URL = "https://api.xiaomimimo.com/v1"
MODEL = "mimo-v2.5"

# 创建一张 200x200 的红色图片
img = Image.new("RGB", (200, 200), color=(255, 0, 0))
buf = io.BytesIO()
img.save(buf, format="PNG")
b64 = base64.b64encode(buf.getvalue()).decode()
img_url = f"data:image/png;base64,{b64}"

print(f"[Test] Model: {MODEL}")
print(f"[Test] Image size: {len(b64)} chars")

headers = {"api-key": API_KEY, "Content-Type": "application/json"}
body = {
    "model": MODEL,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What color is this image? Reply with just the color name in English."},
            {"type": "image_url", "image_url": {"url": img_url}}
        ]
    }],
    "max_tokens": 50
}

print("[Test] Sending request...")
try:
    r = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=body, timeout=60)
    print(f"[Test] Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content", "")
        print(f"✅ Vision works!")
        print(f"   Content: {content}")
        if reasoning:
            print(f"   Reasoning: {reasoning[:200]}")
    else:
        print(f"❌ Error: {r.text[:500]}")
except Exception as e:
    print(f"❌ Exception: {e}")
