"""
CAD AutoPilot 使用示例
展示如何使用视觉 AI 驱动 CAD 自动化
"""

import os
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from superpowers.cad_autopilot import CADAutoPilot


def example_basic_operations():
    """基础操作示例"""
    print("\n" + "=" * 60)
    print("📝 示例 1: 基础操作")
    print("=" * 60)
    
    # 初始化
    autopilot = CADAutoPilot()
    
    # 1. 查看当前屏幕
    print("\n1. 查看当前屏幕状态:")
    state = autopilot.see()
    print(f"   识别到的应用: {state.get('software', '未知')}")
    
    # 2. 查找元素
    print("\n2. 查找 '直线工具':")
    position = autopilot.find("直线工具")
    if position:
        print(f"   位置: {position}")
    
    # 3. 点击元素
    print("\n3. 点击 '直线工具':")
    autopilot.click("直线工具")
    
    # 4. 绘制直线
    print("\n4. 绘制一条直线:")
    autopilot.draw_line((400, 300), (600, 300))
    
    print("\n✅ 基础操作示例完成")


def example_drawing_shapes():
    """绘制图形示例"""
    print("\n" + "=" * 60)
    print("📐 示例 2: 绘制图形")
    print("=" * 60)
    
    autopilot = CADAutoPilot()
    
    # 绘制矩形
    print("\n1. 绘制矩形:")
    autopilot.draw_rect((300, 200), (500, 400))
    
    time.sleep(0.5)
    
    # 绘制圆
    print("\n2. 绘制圆:")
    autopilot.draw_circle((400, 300), (450, 300))
    
    time.sleep(0.5)
    
    # 绘制直线
    print("\n3. 绘制对角线:")
    autopilot.draw_line((300, 200), (500, 400))
    
    print("\n✅ 绘制图形示例完成")


def example_ai_automatic():
    """AI 自动执行示例"""
    print("\n" + "=" * 60)
    print("🤖 示例 3: AI 自动执行")
    print("=" * 60)
    
    autopilot = CADAutoPilot()
    
    # 让 AI 分析屏幕并自动执行任务
    tasks = [
        "在绘图区域中心画一个边长为 100 的正方形",
        "在正方形内画一个内切圆",
        "在圆心位置添加文字 '中心点'"
    ]
    
    for i, task in enumerate(tasks, 1):
        print(f"\n任务 {i}: {task}")
        result = autopilot.execute(task)
        print(f"状态: {result.get('status', '未知')}")
        time.sleep(1)
    
    print("\n✅ AI 自动执行示例完成")


def example_identify_drawing():
    """识别绘图示例"""
    print("\n" + "=" * 60)
    print("🔍 示例 4: 识别绘图")
    print("=" * 60)
    
    autopilot = CADAutoPilot()
    
    # 识别当前绘制的图形
    print("\n识别当前绘图:")
    result = autopilot.identify_drawing()
    
    if result.get("success"):
        analysis = result.get("analysis", {})
        print(f"\n找到的图形元素:")
        for elem in analysis.get("elements", []):
            print(f"  - {elem['type']}: {elem.get('description', '')}")
    else:
        print(f"识别失败: {result.get('error')}")
    
    print("\n✅ 识别绘图示例完成")


def example_interactive():
    """交互式示例"""
    print("\n" + "=" * 60)
    print("🎮 示例 5: 交互式模式")
    print("=" * 60)
    
    autopilot = CADAutoPilot()
    
    print("\n进入交互模式，输入 'quit' 退出")
    print("可用命令:")
    print("  see      - 查看屏幕")
    print("  find X   - 查找元素 X")
    print("  click X  - 点击元素 X")
    print("  line     - 画直线")
    print("  circle   - 画圆")
    print("  rect     - 画矩形")
    print("  undo     - 撤销")
    print("  state    - 获取状态")
    print("  history  - 查看历史")
    
    while True:
        try:
            cmd = input("\nCAD> ").strip().lower()
            
            if cmd == "quit":
                break
            elif cmd == "see":
                autopilot.see()
            elif cmd.startswith("find "):
                autopilot.find(cmd[5:])
            elif cmd.startswith("click "):
                autopilot.click(cmd[6:])
            elif cmd == "line":
                x1, y1 = map(int, input("起点 (x,y): ").split(","))
                x2, y2 = map(int, input("终点 (x,y): ").split(","))
                autopilot.draw_line((x1, y1), (x2, y2))
            elif cmd == "circle":
                cx, cy = map(int, input("圆心 (x,y): ").split(","))
                rx, ry = map(int, input("半径点 (x,y): ").split(","))
                autopilot.draw_circle((cx, cy), (rx, ry))
            elif cmd == "rect":
                x1, y1 = map(int, input("角点1 (x,y): ").split(","))
                x2, y2 = map(int, input("角点2 (x,y): ").split(","))
                autopilot.draw_rect((x1, y1), (x2, y2))
            elif cmd == "undo":
                autopilot.undo()
            elif cmd == "state":
                autopilot.get_state()
            elif cmd == "history":
                autopilot.history()
            else:
                print("未知命令，请重试")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"错误: {e}")
    
    print("\n👋 退出交互模式")


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║              🎮 CAD AutoPilot 使用示例                      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # 检查 API Key
    if not os.getenv("MIMO_API_KEY"):
        print("⚠️  请先设置 MIMO_API_KEY 环境变量")
        print("   set MIMO_API_KEY=your_api_key_here")
        return
    
    print("选择示例:")
    print("1. 基础操作")
    print("2. 绘制图形")
    print("3. AI 自动执行")
    print("4. 识别绘图")
    print("5. 交互式模式")
    print("0. 退出")
    
    choice = input("\n请选择 (0-5): ").strip()
    
    examples = {
        "1": example_basic_operations,
        "2": example_drawing_shapes,
        "3": example_ai_automatic,
        "4": example_identify_drawing,
        "5": example_interactive,
    }
    
    if choice in examples:
        examples[choice]()
    elif choice == "0":
        print("👋 再见！")
    else:
        print("❌ 无效选择")


if __name__ == "__main__":
    main()
