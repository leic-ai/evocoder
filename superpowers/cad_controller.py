"""
CAD Controller — 视觉驱动的 CAD 自动化控制器
通过视觉分析 + 精确操作实现 CAD 自动化建模
"""

import time
import pyautogui
import pyperclip
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from superpowers.vision_engine import VisionEngine, get_vision_engine


class CADCommand(Enum):
    """CAD 常用命令"""
    LINE = "line"
    CIRCLE = "circle"
    ARC = "arc"
    RECTANGLE = "rect"
    POLYGON = "polygon"
    TEXT = "text"
    DIMENSION = "dim"
    MOVE = "move"
    COPY = "copy"
    MIRROR = "mirror"
    OFFSET = "offset"
    TRIM = "trim"
    EXTEND = "extend"
    FILLET = "fillet"
    CHAMFER = "chamfer"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    ZOOM_EXTENTS = "zoom_extents"
    UNDO = "undo"
    REDO = "redo"
    ESCAPE = "escape"
    ENTER = "enter"


@dataclass
class CADAction:
    """CAD 操作记录"""
    command: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    start_pos: Optional[Tuple[int, int]] = None
    end_pos: Optional[Tuple[int, int]] = None
    timestamp: float = field(default_factory=time.time)
    result: str = "pending"


@dataclass
class ScreenState:
    """屏幕状态快照"""
    screenshot_path: str
    analysis: Dict[str, Any]
    timestamp: float


class CADController:
    """视觉驱动的 CAD 控制器"""
    
    def __init__(self, vision_engine: Optional[VisionEngine] = None):
        self.vision = vision_engine or get_vision_engine()
        self.action_history: List[CADAction] = []
        self.state_history: List[ScreenState] = []
        
        # 配置 pyautogui
        pyautogui.FAILSAFE = True  # 鼠标移到左上角紧急停止
        pyautogui.PAUSE = 0.1  # 每个操作间隔 0.1 秒
        
        # CAD 界面元素缓存
        self._ui_cache: Dict[str, Tuple[int, int]] = {}
        
        # 截图保存路径
        self.screenshot_dir = Path("cad_screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)
    
    def capture_screen(self, name: str = "current") -> str:
        """截取当前屏幕"""
        timestamp = int(time.time() * 1000)
        path = str(self.screenshot_dir / f"{name}_{timestamp}.png")
        screenshot = pyautogui.screenshot()
        screenshot.save(path)
        return path
    
    def update_state(self) -> ScreenState:
        """更新并返回当前屏幕状态"""
        screenshot_path = self.capture_screen("state")
        analysis = self.vision.analyze_screenshot(screenshot_path)
        
        state = ScreenState(
            screenshot_path=screenshot_path,
            analysis=analysis,
            timestamp=time.time()
        )
        
        self.state_history.append(state)
        return state
    
    def find_element(self, description: str, use_cache: bool = True) -> Optional[Tuple[int, int]]:
        """在屏幕上查找 UI 元素"""
        if use_cache and description in self._ui_cache:
            return self._ui_cache[description]
        
        screenshot_path = self.capture_screen("find")
        position = self.vision.find_element_position(screenshot_path, description)
        
        if position:
            self._ui_cache[description] = position
        
        return position
    
    def click_element(self, description: str, double_click: bool = False) -> bool:
        """点击指定 UI 元素"""
        position = self.find_element(description)
        
        if position:
            x, y = position
            pyautogui.moveTo(x, y, duration=0.2)
            
            if double_click:
                pyautogui.doubleClick()
            else:
                pyautogui.click()
            
            time.sleep(0.1)
            return True
        
        return False
    
    def type_command(self, command: str, press_enter: bool = True):
        """输入 CAD 命令"""
        # 先按 ESC 确保在命令提示符状态
        pyautogui.press('escape')
        time.sleep(0.05)
        
        # 清除命令行
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.press('delete')
        time.sleep(0.05)
        
        # 输入命令
        pyautogui.write(command, interval=0.02)
        
        if press_enter:
            pyautogui.press('enter')
            time.sleep(0.1)
    
    def click_point(self, x: int, y: int, button: str = 'left'):
        """点击指定坐标"""
        pyautogui.moveTo(x, y, duration=0.15)
        pyautogui.click(button=button)
    
    def draw_line(self, start: Tuple[int, int], end: Tuple[int, int]):
        """绘制直线"""
        self.type_command("line")
        time.sleep(0.2)
        
        # 点击起点
        self.click_point(*start)
        time.sleep(0.1)
        
        # 点击终点
        self.click_point(*end)
        time.sleep(0.1)
        
        # 按 ESC 结束
        pyautogui.press('escape')
        
        self.action_history.append(CADAction(
            command="line",
            start_pos=start,
            end_pos=end,
            result="completed"
        ))
    
    def draw_circle(self, center: Tuple[int, int], radius_point: Tuple[int, int]):
        """绘制圆"""
        self.type_command("circle")
        time.sleep(0.2)
        
        # 点击圆心
        self.click_point(*center)
        time.sleep(0.1)
        
        # 点击半径点
        self.click_point(*radius_point)
        time.sleep(0.1)
        
        self.action_history.append(CADAction(
            command="circle",
            start_pos=center,
            end_pos=radius_point,
            result="completed"
        ))
    
    def draw_rectangle(self, corner1: Tuple[int, int], corner2: Tuple[int, int]):
        """绘制矩形"""
        self.type_command("rect")
        time.sleep(0.2)
        
        # 点击第一个角点
        self.click_point(*corner1)
        time.sleep(0.1)
        
        # 点击对角点
        self.click_point(*corner2)
        time.sleep(0.1)
        
        self.action_history.append(CADAction(
            command="rect",
            start_pos=corner1,
            end_pos=corner2,
            result="completed"
        ))
    
    def zoom_to_element(self, description: str, padding: int = 100):
        """缩放至指定元素"""
        position = self.find_element(description)
        if position:
            x, y = position
            # 先放大
            pyautogui.moveTo(x, y)
            pyautogui.scroll(5)  # 向上滚动放大
            time.sleep(0.2)
    
    def zoom_extents(self):
        """缩放至全部显示"""
        pyautogui.hotkey('ctrl', 'shift', 'z')  # 常见快捷键
        time.sleep(0.3)
    
    def undo(self):
        """撤销"""
        pyautogui.hotkey('ctrl', 'z')
        time.sleep(0.1)
    
    def redo(self):
        """重做"""
        pyautogui.hotkey('ctrl', 'y')
        time.sleep(0.1)
    
    def escape(self):
        """取消当前操作"""
        pyautogui.press('escape')
        time.sleep(0.05)
    
    def get_cursor_position(self) -> Tuple[int, int]:
        """获取当前鼠标位置"""
        return pyautogui.position()
    
    def move_to(self, x: int, y: int, duration: float = 0.2):
        """移动鼠标到指定位置"""
        pyautogui.moveTo(x, y, duration=duration)
    
    def execute_visual_task(self, task_description: str) -> Dict[str, Any]:
        """执行视觉任务 - AI 根据屏幕状态自动完成任务
        
        Args:
            task_description: 任务描述，如 "在绘图区域画一条从左到右的直线"
            
        Returns:
            任务执行结果
        """
        print(f"[CAD] 执行视觉任务: {task_description}")
        
        # 1. 截图并分析当前状态
        screenshot_path = self.capture_screen("task")
        state = self.vision.analyze_screenshot(screenshot_path)
        
        if not state.get("success"):
            return {"error": "无法分析屏幕", "details": state.get("error")}
        
        # 2. 让 AI 规划操作步骤
        plan_prompt = f"""基于当前屏幕状态，规划完成以下任务的操作步骤：

任务：{task_description}

当前屏幕状态：
{state['analysis']}

请返回一个 JSON 格式的操作计划：
{{
    "steps": [
        {{
            "action": "click/type/drag/scroll",
            "target": "目标元素描述",
            "value": "输入的值（如果是输入）",
            "coordinates": {{"x": X, "y": Y}}（如果需要精确坐标）
        }}
    ],
    "estimated_time": 预计完成时间（秒）
}}

只返回 JSON。"""
        
        plan_result = self.vision.analyze_screenshot(screenshot_path, plan_prompt)
        
        return {
            "task": task_description,
            "screen_state": state,
            "plan": plan_result,
            "status": "planned"
        }
    
    def clear_cache(self):
        """清除 UI 元素缓存"""
        self._ui_cache.clear()
    
    def get_history(self) -> List[Dict[str, Any]]:
        """获取操作历史"""
        return [
            {
                "command": action.command,
                "start": action.start_pos,
                "end": action.end_pos,
                "timestamp": action.timestamp,
                "result": action.result
            }
            for action in self.action_history
        ]


# 全局实例
_cad_controller: Optional[CADController] = None


def get_cad_controller() -> CADController:
    """获取 CAD 控制器单例"""
    global _cad_controller
    if _cad_controller is None:
        _cad_controller = CADController()
    return _cad_controller


if __name__ == "__main__":
    print("=== CAD Controller 测试 ===")
    controller = CADController()
    
    # 截取当前屏幕
    screenshot = controller.capture_screen("test")
    print(f"截图已保存: {screenshot}")
    
    # 获取鼠标位置
    pos = controller.get_cursor_position()
    print(f"当前鼠标位置: {pos}")
    
    print("\n✓ CAD Controller 初始化成功")
    print("可用方法:")
    print("  - draw_line(start, end)")
    print("  - draw_circle(center, radius_point)")
    print("  - draw_rectangle(corner1, corner2)")
    print("  - type_command(command)")
    print("  - click_element(description)")
    print("  - execute_visual_task(description)")
