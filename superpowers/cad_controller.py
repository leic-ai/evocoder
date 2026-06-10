"""
CAD Controller — GUI 自动化控制器
使用 pyautogui + 截图 + MiMo 视觉实现 CAD 自动化
"""

import pyautogui
import time
import os
import subprocess
import tempfile
from typing import Optional, Tuple, Dict, Any, List

# 安全设置
pyautogui.FAILSAFE = True  # 鼠标移到左上角可中止
pyautogui.PAUSE = 0.1      # 每个操作间隔


class CADController:
    """CAD GUI 自动化控制器"""
    
    def __init__(self):
        self.screenshot_dir = tempfile.mkdtemp(prefix="cad_auto_")
        self.step_count = 0
        self.history = []
        print(f"[CAD] ✓ 控制器就绪")
        print(f"[CAD]   截图目录: {self.screenshot_dir}")
    
    def screenshot(self, name: str = None) -> str:
        """截取当前屏幕"""
        if name is None:
            name = f"step_{self.step_count:04d}"
        path = os.path.join(self.screenshot_dir, f"{name}.png")
        
        img = pyautogui.screenshot()
        img.save(path)
        self.step_count += 1
        
        return path
    
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1):
        """点击指定位置"""
        print(f"[CAD] 🖱️ 点击 ({x}, {y})")
        pyautogui.click(x, y, button=button, clicks=clicks)
        self.history.append({"action": "click", "x": x, "y": y, "button": button})
        time.sleep(0.2)
    
    def double_click(self, x: int, y: int):
        """双击"""
        self.click(x, y, clicks=2)
    
    def right_click(self, x: int, y: int):
        """右键点击"""
        self.click(x, y, button="right")
    
    def type_text(self, text: str):
        """输入文字"""
        print(f"[CAD] ⌨️ 输入: {text}")
        pyautogui.typewrite(text, interval=0.02)
        self.history.append({"action": "type", "text": text})
        time.sleep(0.1)
    
    def type_chinese(self, text: str):
        """输入中文（通过剪贴板）"""
        print(f"[CAD] ⌨️ 输入中文: {text}")
        import subprocess
        # 用 clip 命令写入剪贴板
        process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
        process.communicate(text.encode('utf-16-le'))
        time.sleep(0.1)
        pyautogui.hotkey('ctrl', 'v')
        self.history.append({"action": "type_chinese", "text": text})
        time.sleep(0.3)
    
    def hotkey(self, *keys):
        """按快捷键"""
        print(f"[CAD] ⌨️ 快捷键: {'+'.join(keys)}")
        pyautogui.hotkey(*keys)
        self.history.append({"action": "hotkey", "keys": list(keys)})
        time.sleep(0.3)
    
    def press(self, key: str, times: int = 1):
        """按单个键"""
        for _ in range(times):
            pyautogui.press(key)
        self.history.append({"action": "press", "key": key, "times": times})
        time.sleep(0.1)
    
    def enter(self):
        """按回车"""
        self.press("enter")
    
    def escape(self):
        """按 Esc"""
        self.press("escape")
    
    def tab(self):
        """按 Tab"""
        self.press("tab")
    
    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5):
        """拖拽"""
        print(f"[CAD] 🖱️ 拖拽 ({x1},{y1}) -> ({x2},{y2})")
        pyautogui.moveTo(x1, y1)
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration)
        self.history.append({"action": "drag", "from": (x1, y1), "to": (x2, y2)})
        time.sleep(0.2)
    
    def scroll(self, x: int, y: int, amount: int):
        """滚动"""
        pyautogui.moveTo(x, y)
        pyautogui.scroll(amount)
        self.history.append({"action": "scroll", "amount": amount})
    
    def move_to(self, x: int, y: int):
        """移动鼠标"""
        pyautogui.moveTo(x, y, duration=0.2)
    
    def wait(self, seconds: float = 1.0):
        """等待"""
        print(f"[CAD] ⏳ 等待 {seconds}秒")
        time.sleep(seconds)
    
    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕分辨率"""
        return pyautogui.size()
    
    def get_mouse_pos(self) -> Tuple[int, int]:
        """获取鼠标位置"""
        return pyautogui.position()
    
    def get_history(self) -> List[Dict]:
        """获取操作历史"""
        return self.history.copy()


if __name__ == "__main__":
    ctrl = CADController()
    w, h = ctrl.get_screen_size()
    print(f"\n屏幕分辨率: {w} x {h}")
    print(f"鼠标位置: {ctrl.get_mouse_pos()}")
