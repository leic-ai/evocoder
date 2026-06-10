"""
Vision Engine — 多模态视觉分析引擎
使用 MiMo Vision API 实现屏幕理解和 CAD 自动化
"""

import base64
import json
import os
import time
import io
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from openai import OpenAI


class VisionEngine:
    """视觉分析引擎 - 让 EvoCoder 能够'看懂'屏幕
    
    使用 MiMo mimo-v2.5 推理模型的视觉能力。
    注意：mimo-v2.5 是推理模型，输出可能在 reasoning_content 字段中。
    """
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("MIMO_API_KEY") or "sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g"
        self.base_url = base_url or os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
        self.preferred_model = model or os.getenv("MIMO_MODEL", "mimo-v2.5")
        
        if not self.api_key:
            raise ValueError("需要设置 MIMO_API_KEY 环境变量或传入 api_key 参数")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # 已知支持视觉的模型
        self.vision_models = [
            "mimo-v2.5",
            "mimo-v2.5-pro",
            "mimo-v2.5-pro-vision",
            "mimo-v2.5-vision", 
        ]
        
        self.current_model = None
        self._detect_available_model()
    
    def _detect_available_model(self):
        """检测可用的视觉模型 - 用纯文本快速检测"""
        # 优先使用用户指定的模型
        if self.preferred_model:
            try:
                test_response = self.client.chat.completions.create(
                    model=self.preferred_model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5
                )
                self.current_model = self.preferred_model
                print(f"[Vision] ✓ 使用模型: {self.current_model}")
                return
            except Exception as e:
                print(f"[Vision] ⚠ 指定模型 {self.preferred_model} 不可用: {e}")
        
        # 尝试其他视觉模型
        for model in self.vision_models:
            if model == self.preferred_model:
                continue
            try:
                test_response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5
                )
                self.current_model = model
                print(f"[Vision] ✓ 使用模型: {self.current_model}")
                return
            except Exception as e:
                print(f"[Vision] ⚠ 模型 {model} 不可用: {e}")
                continue
        
        raise RuntimeError("没有找到可用的视觉模型")
    
    def _extract_content(self, response) -> str:
        """从响应中提取内容（兼容推理模型格式）
        
        MiMo v2.5 是推理模型，输出可能在：
        - message.content: 正常输出
        - message.reasoning_content: 推理过程
        """
        choice = response.choices[0]
        msg = choice.message
        
        # 优先使用 content
        if msg.content and msg.content.strip():
            return msg.content.strip()
        
        # 如果 content 为空，尝试 reasoning_content
        if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
            return msg.reasoning_content.strip()
        
        return ""
    
    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> str:
        """截取屏幕并返回 base64 编码的 PNG 图片
        
        Args:
            region: 可选的截图区域 (x, y, width, height)
            
        Returns:
            base64 编码的 PNG 图片字符串
        """
        try:
            import pyautogui
            from PIL import Image
            
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            # 转换为 base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG")
            buffer.seek(0)
            return base64.b64encode(buffer.read()).decode()
            
        except ImportError:
            raise RuntimeError("需要安装 pyautogui 和 Pillow: pip install pyautogui Pillow")
    
    def encode_image(self, image_path: str) -> str:
        """将图片文件编码为 base64
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            base64 编码的图片字符串
        """
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    
    def analyze_image(
        self,
        image: str,
        prompt: str,
        image_format: str = "png",
        is_base64: bool = True,
        max_tokens: int = 1024
    ) -> Dict[str, Any]:
        """分析图片内容
        
        Args:
            image: base64 编码的图片或图片文件路径
            prompt: 分析提示词
            image_format: 图片格式 (png, jpg, etc.)
            is_base64: 是否为 base64 编码
            max_tokens: 最大输出 token 数
            
        Returns:
            分析结果字典
        """
        # 准备图片数据
        if is_base64:
            b64_data = image
        else:
            b64_data = self.encode_image(image)
        
        # 构造消息
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{image_format};base64,{b64_data}"
                        }
                    }
                ]
            }
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.current_model,
                messages=messages,
                max_tokens=max_tokens
            )
            
            content = self._extract_content(response)
            
            return {
                "success": True,
                "content": content,
                "model": self.current_model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "model": self.current_model
            }
    
    def analyze_screen(
        self,
        prompt: str,
        region: Optional[Tuple[int, int, int, int]] = None,
        max_tokens: int = 1024
    ) -> Dict[str, Any]:
        """分析当前屏幕内容
        
        Args:
            prompt: 分析提示词
            region: 可选的截图区域 (x, y, width, height)
            max_tokens: 最大输出 token 数
            
        Returns:
            分析结果字典
        """
        try:
            screenshot_b64 = self.capture_screen(region)
        except Exception as e:
            return {
                "success": False,
                "error": f"截图失败: {e}"
            }
        
        # 简化提示词，聚焦 CAD 识别
        cad_prompt = f"""你是一个专业的 CAD 软件识别助手。请分析这个屏幕截图。

{prompt}

请用简洁的中文回答。"""
        
        return self.analyze_image(
            image=screenshot_b64,
            prompt=cad_prompt,
            max_tokens=max_tokens
        )
    
    def identify_software(self) -> str:
        """识别当前屏幕上运行的 CAD 软件"""
        result = self.analyze_screen(
            prompt="请识别当前屏幕上的 CAD 软件名称，只回答软件名称（如 AutoCAD、SolidWorks、Fusion360 等）",
            max_tokens=50
        )
        if result["success"]:
            return result["content"]
        return "unknown"
    
    def find_element(self, description: str) -> Optional[Tuple[int, int]]:
        """在屏幕上查找指定的 UI 元素
        
        Args:
            description: 元素描述（如"直线工具"、"File 菜单"）
            
        Returns:
            元素的坐标 (x, y)，未找到返回 None
        """
        result = self.analyze_screen(
            prompt=f"""请在屏幕上找到 "{description}" 的位置。
请用以下 JSON 格式回答，不要有多余文字：
{{"found": true, "x": 像素x坐标, "y": 像素y坐标}}
如果找不到：
{{"found": false}}""",
            max_tokens=100
        )
        
        if not result["success"]:
            return None
        
        try:
            content = result["content"]
            # 尝试提取 JSON
            import re
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                data = json.loads(json_match.group())
                if data.get("found"):
                    return (data["x"], data["y"])
        except (json.JSONDecodeError, KeyError):
            pass
        
        return None
    
    def get_screen_state(self) -> Dict[str, Any]:
        """获取当前屏幕的完整状态描述"""
        result = self.analyze_screen(
            prompt="""请详细描述当前屏幕状态，包括：
1. 当前软件名称
2. 当前工具/模式
3. 可见的菜单栏和工具栏
4. 绘图区域的内容描述
5. 当前的对话框或弹出窗口（如有）

请用 JSON 格式回答。""",
            max_tokens=500
        )
        
        if not result["success"]:
            return {"error": result.get("error", "未知错误")}
        
        try:
            # 尝试解析 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', result["content"])
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        # 返回原始文本
        return {"description": result["content"]}
    
    def execute_visual_task(self, task: str) -> Dict[str, Any]:
        """执行一个视觉任务 - 分析屏幕并返回执行建议
        
        Args:
            task: 任务描述（如"画一个矩形"）
            
        Returns:
            任务执行建议
        """
        result = self.analyze_screen(
            prompt=f"""你是一个 CAD 自动化助手。当前需要完成以下任务：

任务：{task}

请分析当前屏幕状态，并给出执行该任务的详细步骤。用 JSON 格式回答：
{{
    "current_state": "当前屏幕状态描述",
    "software": "软件名称",
    "steps": [
        {{"action": "click", "target": "目标描述", "coordinates": [x, y]}},
        {{"action": "type", "text": "要输入的文字"}},
        {{"action": "shortcut", "keys": "快捷键组合"}},
        ...
    ]
}}""",
            max_tokens=800
        )
        
        if not result["success"]:
            return {"error": result.get("error", "未知错误")}
        
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', result["content"])
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        return {"raw_response": result["content"]}


# 快速测试
if __name__ == "__main__":
    print("=" * 60)
    print("🔍 MiMo Vision Engine 测试")
    print("=" * 60)
    
    try:
        engine = VisionEngine()
        
        # 测试 1: 分析本地图片
        print("\n[1] 测试图片分析...")
        
        # 创建测试图片
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (200, 200), "white")
            draw = ImageDraw.Draw(img)
            draw.rectangle([50, 50, 150, 150], fill="blue")
            
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode()
            
            result = engine.analyze_image(
                image=b64,
                prompt="这张图片画了什么？请描述。"
            )
            print(f"   结果: {result}")
        except ImportError:
            print("   ⚠ 需要 Pillow 进行图片测试")
        
        # 测试 2: 文本生成
        print("\n[2] 测试文本生成...")
        text_result = engine.client.chat.completions.create(
            model=engine.current_model,
            messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}],
            max_tokens=100
        )
        print(f"   结果: {engine._extract_content(text_result)}")
        
        print("\n✅ 测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
