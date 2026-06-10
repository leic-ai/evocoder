"""Test API connectivity (MiMo or DeepSeek)"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
base_url = "https://api.xiaomimimo.com/v1" if os.getenv("MIMO_API_KEY") else "https://api.deepseek.com"
model = "mimo-v2.5-pro" if os.getenv("MIMO_API_KEY") else "deepseek-chat"

client = OpenAI(api_key=api_key, base_url=base_url, timeout=30)

response = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Say hello in 5 words"}],
    max_tokens=50,
)
print(f"Model: {response.model}")
print(f"Response: {response.choices[0].message.content}")
print(f"Tokens: {response.usage}")
print("API OK!")
