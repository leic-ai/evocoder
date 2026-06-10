"""
CAD AutoPilot 使用示例
"""

from cad_autopilot import CADAutoPilot


def demo_basic():
    """基础演示：看屏幕"""
    print("=" * 50)
    print("  CAD AutoPilot — 基础演示")
    print("=" * 50)
    
    autopilot = CADAutoPilot()
    
    # 看当前屏幕
    screen = autopilot.look()
    print(f"\n屏幕内容:\n{screen}")


def demo_draw_line():
    """演示：在 CAD 中画一条线"""
    autopilot = CADAutoPilot()
    
    # 设置目标
    autopilot.set_goal("在 CAD 中画一条从 (100,100) 到 (500,500) 的直线")
    
    # 开始执行
    autopilot.run(max_steps=20)


def demo_draw_circle():
    """演示：在 CAD 中画一个圆"""
    autopilot = CADAutoPilot()
    
    autopilot.set_goal(
        "在 CAD 中画一个圆心在 (300,300)，半径 100 的圆"
    )
    autopilot.run(max_steps=20)


def demo_custom():
    """自定义目标"""
    autopilot = CADAutoPilot()
    
    # 输入你的目标
    goal = input("请输入 CAD 操作目标: ").strip()
    if goal:
        autopilot.set_goal(goal)
        autopilot.run(max_steps=30)
    else:
        print("未输入目标，退出")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "line":
            demo_draw_line()
        elif cmd == "circle":
            demo_draw_circle()
        elif cmd == "look":
            demo_basic()
        elif cmd == "custom":
            demo_custom()
        else:
            print(f"未知命令: {cmd}")
            print("用法: python cad_examples.py [line|circle|look|custom]")
    else:
        print("CAD AutoPilot 示例")
        print("=" * 30)
        print("1. look    - 看屏幕")
        print("2. line    - 画直线")
        print("3. circle  - 画圆")
        print("4. custom  - 自定义目标")
        print()
        cmd = input("选择 (1-4): ").strip()
        if cmd == "1":
            demo_basic()
        elif cmd == "2":
            demo_draw_line()
        elif cmd == "3":
            demo_draw_circle()
        elif cmd == "4":
            demo_custom()
