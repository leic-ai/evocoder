"""Test DeepSeek API connectivity"""
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Say hello in 5 words"}],
    max_tokens=50,
)
print(f"Model: {response.model}")
print(f"Response: {response.choices[0].message.content}")
print(f"Tokens: {response.usage}")
print("API OK!")
