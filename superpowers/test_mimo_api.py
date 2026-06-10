"""Test MiMo API connection"""
import os
from openai import OpenAI

client = OpenAI(
    api_key="sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g",
    base_url="https://api.xiaomimimo.com/v1"
)

print("[1] Testing text generation...")
try:
    resp = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=[{"role": "user", "content": "Hello, respond with just: OK"}],
        max_tokens=10
    )
    print(f"  Text OK: {resp.choices[0].message.content}")
except Exception as e:
    print(f"  Text FAILED: {e}")

print("\n[2] Testing vision (multimodal)...")
try:
    import base64
    # Create a small test image
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    
    resp = client.chat.completions.create(
        model="mimo-v2.5-pro",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is this image? Reply with just the color name."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            ]
        }],
        max_tokens=20
    )
    print(f"  Vision OK: {resp.choices[0].message.content}")
except Exception as e:
    print(f"  Vision FAILED: {e}")

print("\nDone!")
