"""
CAD AutoPilot — 一键式 CAD 自动化接口
让 EvoCoder 能够"看屏幕"并操作 CAD
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from superpowers.vision_engine import VisionEngine
from superpowers.cad_controller import CADController


class CADAutoPilot:
    """CAD 自动驾驶仪 - AI 驱动的 CAD 自动化"""
    
    # 默认配置
    DEFAULT_API_KEY = "sk-coyrt3ynsv5n2yttjza2c0z6dpui199pbi5uoabx6w6dek2g"
    DEFAULT_BASE_URL = "https://api.xiaomimimo.com/v1"
    DEFAULT_MODEL = "mimo-v2.5"
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        """初始化 CAD AutoPilot
        
        Args:
            api_key: MiMo API Key，如果未提供则使用默认值
            base_url: API 基础 URL
            model: 视觉模型名称
        """
        print("=" * 60)
        print("🚀 CAD AutoPilot 初始化中...")
        print("=" * 60)
        
        # 初始化视觉引擎
        self.vision = VisionEngine(
            api_key=api_key or self.DEFAULT_API_KEY,
            base_url=base_url or self.DEFAULT_BASE_URL,
            model=model or self.DEFAULT_MODEL
        )
        print(f"✓ 视觉引擎就绪 (模型: {self.vision.current_model})")
        
        # 初始化 CAD 控制器
        self.controller = CADController(self.vision)
        print("✓ CAD 控制器就绪")
        
        # 创建工作目录
        self.workspace = Path("cad_workspace")
        self.workspace.mkdir(exist_ok=True)
        
        print("=" * 60)
        print("✅ CAD AutoPilot 初始化完成！")
        print("=" * 60)
    
    def see(self) -> Dict[str, Any]:
        """'看'当前屏幕并返回分析结果"""
        print("\n📸 正在截图并分析...")
        screenshot = self.controller.capture_screen("see")
        result = self.vision.analyze_screenshot(screenshot)
        
        if result.get("success"):
            print("✓ 识别完成")
            return result["analysis"]
        else:
            print(f"✗ 识别失败: {result.get('error')}")
            return {"error": result.get("error")}
    
    def find(self, element: str) -> Optional[tuple]:
        """在屏幕上查找指定元素"""
        print(f"\n🔍 正在查找: {element}")
        position = self.controller.find_element(element)
        
        if position:
            print(f"✓ 找到位置: ({position[0]}, {position[1]})")
        else:
            print("✗ 未找到该元素")
        
        return position
    
    def click(self, element_or_x, y: Optional[int] = None):
        """点击元素或坐标"""
        if isinstance(element_or_x, str):
            print(f"\n🖱️ 点击元素: {element_or_x}")
            success = self.controller.click_element(element_or_x)
            if success:
                print("✓ 点击成功")
            else:
                print("✗ 点击失败 - 未找到元素")
        else:
            print(f"\n🖱️ 点击坐标: ({element_or_x}, {y})")
            self.controller.click_point(element_or_x, y)
            print("✓ 点击完成")
    
    def type(self, text: str, press_enter: bool = True):
        """输入文字或命令"""
        print(f"\n⌨️ 输入: {text}")
        self.controller.type_command(text, press_enter)
        print("✓ 输入完成")
    
    def draw_line(self, start: tuple, end: tuple):
        """绘制直线"""
        print(f"\n📏 绘制直线: {start} -> {end}")
        self.controller.draw_line(start, end)
        print("✓ 直线绘制完成")
    
    def draw_circle(self, center: tuple, radius_point: tuple):
        """绘制圆"""
        print(f"\n⭕ 绘制圆: 中心{center}, 半径点{radius_point}")
        self.controller.draw_circle(center, radius_point)
        print("✓ 圆绘制完成")
    
    def draw_rect(self, corner1: tuple, corner2: tuple):
        """绘制矩形"""
        print(f"\n⬜ 绘制矩形: {corner1} -> {corner2}")
        self.controller.draw_rectangle(corner1, corner2)
        print("✓ 矩形绘制完成")
    
    def undo(self):
        """撤销操作"""
        print("\n↩️ 撤销")
        self.controller.undo()
    
    def redo(self):
        """重做操作"""
        print("\n↪️ 重做")
        self.controller.redo()
    
    def escape(self):
        """取消当前操作"""
        print("\n❌ 取消操作")
        self.controller.escape()
    
    def zoom_all(self):
        """缩放至全部显示"""
        print("\n🔍 缩放至全部")
        self.controller.zoom_extents()
    
    def get_state(self) -> Dict[str, Any]:
        """获取当前 CAD 状态"""
        screenshot = self.controller.capture_screen("state")
        return self.vision.get_cad_state(screenshot)
    
    def identify_drawing(self) -> Dict[str, Any]:
        """识别当前绘制的图形"""
        print("\n🔍 识别图形中...")
        screenshot = self.controller.capture_screen("identify")
        return self.vision.identify_drawing(screenshot)
    
    def execute(self, task: str) -> Dict[str, Any]:
        """让 AI 自动执行任务"""
        print(f"\n🤖 执行任务: {task}")
        return self.controller.execute_visual_task(task)
    
    def history(self):
        """显示操作历史"""
        history = self.controller.get_history()
        print(f"\n📜 操作历史 ({len(history)} 条):")
        for i, action in enumerate(history, 1):
            print(f"  {i}. {action['command']}: {action.get('start', '')} -> {action.get('end', '')}")


def main():
    """主函数 - 启动 CAD AutoPilot"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    🎮 CAD AutoPilot                        ║
║              AI 驱动的 CAD 自动化系统                       ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # 检查 API Key
    api_key = os.getenv("MIMO_API_KEY")
    if not api_key:
        print("⚠️  未找到 MIMO_API_KEY 环境变量")
        print("请设置: set MIMO_API_KEY=your_api_key")
        print("或在初始化时传入: CADAutoPilot(api_key='your_key')")
        return
    
    try:
        # 初始化
        autopilot = CADAutoPilot(api_key)
        
        # 显示当前屏幕状态
        print("\n📸 分析当前屏幕...")
        state = autopilot.see()
        
        if "error" not in state:
            print("\n当前屏幕状态:")
            print(json.dumps(state, indent=2, ensure_ascii=False)[:500] + "...")
        
        print("\n" + "=" * 60)
        print("✅ CAD AutoPilot 已就绪！")
        print("=" * 60)
        print("\n常用方法:")
        print("  autopilot.see()          # 查看屏幕")
        print("  autopilot.find('元素')    # 查找元素")
        print("  autopilot.click('元素')   # 点击元素")
        print("  autopilot.draw_line(...)  # 画直线")
        print("  autopilot.draw_circle(...) # 画圆")
        print("  autopilot.type('命令')    # 输入命令")
        print("  autopilot.execute('任务') # AI 自动执行")
        print("=" * 60)
        
        # 保持交互
        return autopilot
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    autopilot = main()
