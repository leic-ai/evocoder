"""
CAD AutoPilot — 视觉驱动的 CAD 自动化系统

流程: 截屏 → MiMo 视觉分析 → 生成操作 → 执行 → 重复

就像人类一样：看屏幕 → 思考 → 动手操作
"""

import time
import json
import re
from typing import Optional, Dict, Any, List
from vision_engine import VisionEngine
from cad_controller import CADController


class CADAutoPilot:
    """视觉驱动的 CAD 自动化系统"""
    
    def __init__(self, api_key: str = None, model: str = None):
        print("=" * 50)
        print("  CAD AutoPilot — 视觉驱动自动化系统")
        print("=" * 50)
        
        self.vision = VisionEngine(api_key=api_key, model=model)
        self.ctrl = CADController()
        self.goal = ""
        self.max_steps = 50
        self.step_delay = 1.0
        self.verbose = True
        self.running = False
        
        # CAD 软件上下文
        self.cad_context = {
            "software": "unknown",
            "current_tool": None,
            "objects_created": [],
        }
        
        print("[AutoPilot] ✓ 系统就绪\n")
    
    def set_goal(self, goal: str):
        """设置目标"""
        self.goal = goal
        print(f"[AutoPilot] 🎯 目标: {goal}")
    
    def look(self) -> str:
        """看屏幕 — 截屏并分析"""
        print(f"\n{'='*40}")
        print(f"[步骤 {self.ctrl.step_count}] 📸 截屏分析中...")
        
        result = self.vision.capture_and_analyze(
            prompt=self._build_look_prompt(),
            max_tokens=2000
        )
        
        if result.get("success"):
            description = result["content"]
            if self.verbose:
                print(f"[Vision] 👁️ 看到了: {description[:200]}...")
            return description
        else:
            error = result.get("error", "未知错误")
            print(f"[Vision] ❌ 分析失败: {error}")
            return f"分析失败: {error}"
    
    def think(self, screen_description: str) -> Dict[str, Any]:
        """思考 — 基于屏幕内容决定下一步"""
        prompt = self._build_think_prompt(screen_description)
        
        result = self.vision.capture_and_analyze(prompt=prompt, max_tokens=800)
        
        if not result.get("success"):
            return {"action": "wait", "reason": "分析失败，等待重试"}
        
        content = result["content"]
        
        # 尝试解析 JSON 操作指令
        action = self._parse_action(content)
        if action:
            return action
        
        # 如果解析失败，返回原始内容
        return {"action": "unknown", "raw": content, "reason": "无法解析操作"}
    
    def act(self, action: Dict[str, Any]) -> bool:
        """执行操作"""
        act_type = action.get("action", "unknown")
        reason = action.get("reason", "")
        
        print(f"[Action] 🎬 {act_type}: {reason}")
        
        try:
            if act_type == "click":
                x, y = action.get("x", 0), action.get("y", 0)
                if x > 0 and y > 0:
                    self.ctrl.click(x, y)
                else:
                    print(f"[Action] ⚠️ 无效坐标 ({x}, {y})")
                    return False
            
            elif act_type == "double_click":
                x, y = action.get("x", 0), action.get("y", 0)
                self.ctrl.double_click(x, y)
            
            elif act_type == "right_click":
                x, y = action.get("x", 0), action.get("y", 0)
                self.ctrl.right_click(x, y)
            
            elif act_type == "type":
                text = action.get("value", "")
                if text:
                    self.ctrl.type_text(text)
            
            elif act_type == "type_chinese":
                text = action.get("value", "")
                if text:
                    self.ctrl.type_chinese(text)
            
            elif act_type == "hotkey":
                key = action.get("key", "")
                if "+" in key:
                    keys = key.split("+")
                    self.ctrl.hotkey(*keys)
                else:
                    self.ctrl.press(key)
            
            elif act_type == "drag":
                x1 = action.get("x1", 0)
                y1 = action.get("y1", 0)
                x2 = action.get("x2", 0)
                y2 = action.get("y2", 0)
                self.ctrl.drag(x1, y1, x2, y2)
            
            elif act_type == "scroll":
                x = action.get("x", 960)
                y = action.get("y", 540)
                amount = action.get("amount", 3)
                self.ctrl.scroll(x, y, amount)
            
            elif act_type == "wait":
                self.ctrl.wait(1.0)
            
            elif act_type == "done":
                print(f"\n[AutoPilot] ✅ 目标完成！")
                return True
            
            elif act_type == "enter":
                self.ctrl.enter()
            
            elif act_type == "escape":
                self.ctrl.escape()
            
            elif act_type == "tab":
                self.ctrl.tab()
            
            else:
                print(f"[Action] ⚠️ 未知操作: {act_type}")
                return False
            
            return False  # 未完成，继续
            
        except Exception as e:
            print(f"[Action] ❌ 执行失败: {e}")
            return False
    
    def run(self, goal: str = None, max_steps: int = None):
        """运行自动化循环"""
        if goal:
            self.set_goal(goal)
        if max_steps:
            self.max_steps = max_steps
        
        if not self.goal:
            print("[AutoPilot] ❌ 未设置目标！")
            return
        
        self.running = True
        step = 0
        
        print(f"\n[AutoPilot] 🚀 开始执行...")
        print(f"[AutoPilot] 最大步数: {self.max_steps}\n")
        
        while self.running and step < self.max_steps:
            step += 1
            print(f"\n--- 循环 {step}/{self.max_steps} ---")
            
            # 1. 看
            screen_desc = self.look()
            
            # 2. 想
            action = self.think(screen_desc)
            print(f"[Think] 💭 决策: {json.dumps(action, ensure_ascii=False)[:200]}")
            
            # 3. 做
            done = self.act(action)
            
            if done:
                print(f"\n[AutoPilot] 🎉 任务完成！共 {step} 步")
                break
            
            # 4. 等待
            time.sleep(self.step_delay)
        
        if step >= self.max_steps:
            print(f"\n[AutoPilot] ⚠️ 达到最大步数 ({self.max_steps})")
        
        self.running = False
    
    def stop(self):
        """停止"""
        self.running = False
        print("[AutoPilot] ⏹️ 已停止")
    
    def _build_look_prompt(self) -> str:
        return (
            "请详细描述当前屏幕截图的内容。\n"
            "重点关注：\n"
            "1. 这是什么软件？（CAD/SolidWorks/其他）\n"
            "2. 顶部菜单栏有什么选项？\n"
            "3. 左侧工具栏有什么工具？\n"
            "4. 中间绘图区域的内容\n"
            "5. 命令行/状态栏显示什么\n"
            "6. 当前鼠标位置附近有什么\n"
            "请用中文简洁描述。"
        )
    
    def _build_think_prompt(self, screen_description: str) -> str:
        w, h = self.ctrl.get_screen_size()
        return (
            f"你是 CAD 自动化助手。\n\n"
            f"当前目标：{self.goal}\n\n"
            f"屏幕分辨率：{w}x{h}\n\n"
            f"当前屏幕描述：\n{screen_description[:500]}\n\n"
            f"请决定下一步操作。返回严格的 JSON 格式：\n"
            f'{{"action": "操作类型", "x": 数字, "y": 数字, "value": "文字", "key": "快捷键", "reason": "原因"}}\n\n'
            f"支持的 action 类型：\n"
            f'- click: 点击 (需要 x, y)\n'
            f'- double_click: 双击 (需要 x, y)\n'  
            f'- right_click: 右键 (需要 x, y)\n'
            f'- type: 输入英文/数字 (需要 value)\n'
            f'- type_chinese: 输入中文 (需要 value)\n'
            f'- hotkey: 快捷键 (需要 key, 如 "ctrl+z")\n'
            f'- drag: 拖拽 (需要 x1,y1,x2,y2)\n'
            f'- scroll: 滚动 (需要 x, y, amount)\n'
            f'- enter: 回车\n'
            f'- escape: ESC\n'
            f'- wait: 等待\n'
            f'- done: 任务已完成\n\n'
            f"坐标必须在屏幕范围内（0-{w}, 0-{h}）。\n"
            f"只返回 JSON，不要其他文字。"
        )
    
    def _parse_action(self, content: str) -> Optional[Dict]:
        """从 AI 输出中解析操作指令"""
        try:
            # 尝试直接解析
            action = json.loads(content.strip())
            return action
        except:
            pass
        
        # 尝试提取 JSON
        try:
            # 移除 markdown 代码块
            cleaned = re.sub(r'```json?\s*', '', content)
            cleaned = re.sub(r'```\s*', '', cleaned)
            
            # 找到 JSON 对象
            match = re.search(r'\{[^{}]*\}', cleaned, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
        
        # 尝试从中文描述中提取坐标
        coord_match = re.search(r'(\d{2,4})\s*[,.]\s*(\d{2,4})', content)
        if coord_match:
            return {
                "action": "click",
                "x": int(coord_match.group(1)),
                "y": int(coord_match.group(2)),
                "reason": "从描述中提取坐标"
            }
        
        return None
    
    def get_summary(self) -> str:
        """获取操作摘要"""
        history = self.ctrl.get_history()
        summary = f"共执行 {len(history)} 步操作：\n"
        for i, h in enumerate(history[:20], 1):
            summary += f"  {i}. {h['action']}"
            if 'x' in h and 'y' in h:
                summary += f" ({h['x']},{h['y']})"
            if 'text' in h:
                summary += f" '{h['text']}'"
            summary += "\n"
        if len(history) > 20:
            summary += f"  ... 还有 {len(history)-20} 步"
        return summary


if __name__ == "__main__":
    # 快速测试
    autopilot = CADAutoPilot()
    
    # 测试视觉
    print("\n[测试] 截屏并分析...")
    screen = autopilot.look()
    print(f"\n屏幕描述:\n{screen[:500]}")
