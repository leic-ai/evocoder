"""
Vision Engine — 多模态视觉分析引擎
使用小米 MiMo mimo-v2.5 视觉模型
"""

import base64
import io
import os
import json
import time
import subprocess
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

import requests
from PIL import Image


class VisionEngine:
    """视觉分析引擎 — 让 EvoCoder 能"看懂"屏幕
    
    使用小米 MiMo mimo-v2.5 多模态视觉模型。
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("MIMO_API_KEY", "sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g")
        self.base_url = base_url or os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
        self.model = model or os.getenv("MIMO_MODEL", "mimo-v2.5")
        self.chat_url = f"{self.base_url}/chat/completions"
        
        if not self.api_key:
            raise ValueError("需要设置 MIMO_API_KEY")
        
        print(f"[Vision] ✓ 初始化完成")
        print(f"[Vision]   模型: {self.model}")
        print(f"[Vision]   API: {self.base_url}")
    
    def _headers(self):
        return {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def screenshot_to_base64(self, screenshot_path: str = None) -> str:
        """截屏并转为 base64"""
        if screenshot_path is None:
            screenshot_path = os.path.join(os.environ.get("TEMP", "."), f"vision_capture_{int(time.time())}.png")
            # 用 PowerShell 截屏
            ps_cmd = f'''
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
            $bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
            $bitmap.Save("{screenshot_path.replace(chr(92), chr(92)+chr(92))}")
            $graphics.Dispose()
            $bitmap.Dispose()
            '''
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=10)
        
        if not os.path.exists(screenshot_path):
            raise FileNotFoundError(f"截图文件不存在: {screenshot_path}")
        
        with open(screenshot_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        
        return b64
    
    def analyze_image(self, image_path: str, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """分析单张图片"""
        b64 = self.screenshot_to_base64(image_path)
        img_url = f"data:image/png;base64,{b64}"
        
        body = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": img_url}}
                ]
            }],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        try:
            r = requests.post(self.chat_url, headers=self._headers(), json=body, timeout=120)
            if r.status_code == 200:
                data = r.json()
                msg = data["choices"][0]["message"]
                return {
                    "success": True,
                    "content": msg.get("content", ""),
                    "reasoning": msg.get("reasoning_content", ""),
                    "model": data.get("model", self.model)
                }
            else:
                return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def capture_and_analyze(self, prompt: str, max_tokens: int = 1000) -> Dict[str, Any]:
        """截屏并分析"""
        print(f"[Vision] 📸 截屏中...")
        b64 = self.screenshot_to_base64()
        img_url = f"data:image/png;base64,{b64}"
        
        body = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": img_url}}
                ]
            }],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        print(f"[Vision] 🔍 分析中...")
        try:
            r = requests.post(self.chat_url, headers=self._headers(), json=body, timeout=120)
            if r.status_code == 200:
                data = r.json()
                msg = data["choices"][0]["message"]
                return {
                    "success": True,
                    "content": msg.get("content", ""),
                    "reasoning": msg.get("reasoning_content", ""),
                }
            else:
                return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:300]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def see(self) -> str:
        """看屏幕，返回描述"""
        prompt = (
            "请详细描述当前屏幕内容。"
            "1. 这是什么软件？"
            "2. 界面布局如何？（工具栏、菜单栏、绘图区域等的位置）"
            "3. 当前选中了什么工具？"
            "4. 绘图区域有什么内容？"
            "请用中文回答。"
        )
        result = self.capture_and_analyze(prompt, max_tokens=1500)
        return result.get("content", result.get("error", "分析失败"))
    
    def find_element(self, description: str) -> Optional[Tuple[int, int]]:
        """在屏幕上查找UI元素并返回坐标"""
        prompt = (
            f"请在屏幕截图中找到「{description}」的位置。\n"
            f"屏幕分辨率信息：宽度约1920像素，高度约1080像素。\n"
            f"请返回该元素中心的像素坐标，格式为：X:数字,Y:数字\n"
            f"如果找不到，返回：NOT_FOUND"
        )
        result = self.capture_and_analyze(prompt, max_tokens=100)
        content = result.get("content", "")
        
        # 解析坐标
        import re
        match = re.search(r'X:\s*(\d+)\s*,\s*Y:\s*(\d+)', content)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return None
    
    def analyze_for_action(self, goal: str) -> Dict[str, Any]:
        """分析屏幕并返回下一步操作建议"""
        prompt = (
            f"你是一个CAD自动化助手。当前目标：{goal}\n\n"
            f"请分析当前屏幕截图，然后返回JSON格式的操作指令：\n"
            f'{{"action": "click|type|hotkey|drag|done", "target": "元素描述", "x": 数字, "y": 数字, "value": "输入内容", "key": "快捷键", "reason": "原因"}}\n\n'
            f"坐标基于屏幕分辨率1920x1080。\n"
            f"如果目标已完成，返回 action=done。\n"
            f"只返回JSON，不要其他文字。"
        )
        result = self.capture_and_analyze(prompt, max_tokens=500)
        content = result.get("content", "")
        
        # 尝试解析JSON
        try:
            # 找到JSON部分
            import re
            json_match = re.search(r'\{[^{}]*\}', content)
            if json_match:
                return {"success": True, "action": json.loads(json_match.group())}
            return {"success": False, "raw": content}
        except:
            return {"success": False, "raw": content}


# 全局实例
_vision_engine = None

def get_vision_engine() -> VisionEngine:
    global _vision_engine
    if _vision_engine is None:
        _vision_engine = VisionEngine()
    return _vision_engine


if __name__ == "__main__":
    engine = VisionEngine()
    print("\n[测试] 分析图片...")
    result = engine.analyze_image("test_image.png", "描述这张图片") if os.path.exists("test_image.png") else None
    if result:
        print(f"结果: {result}")
    else:
        print("[测试] 没有测试图片，跳过")
