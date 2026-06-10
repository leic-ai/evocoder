"""快速测试 CAD AutoPilot 系统"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    print("测试导入...")
    try:
        from superpowers.vision_engine import VisionEngine
        print("✓ VisionEngine 导入成功")
    except Exception as e:
        print(f"✗ VisionEngine 导入失败: {e}")
        return False
    
    try:
        from superpowers.cad_controller import CADController
        print("✓ CADController 导入成功")
    except Exception as e:
        print(f"✗ CADController 导入失败: {e}")
        return False
    
    try:
        from superpowers.cad_autopilot import CADAutoPilot
        print("✓ CADAutoPilot 导入成功")
    except Exception as e:
        print(f"✗ CADAutoPilot 导入失败: {e}")
        return False
    
    return True

def test_pyautogui():
    print("\n测试 pyautogui...")
    try:
        import pyautogui
        pos = pyautogui.position()
        print(f"✓ pyautogui 正常，当前鼠标位置: {pos}")
        return True
    except Exception as e:
        print(f"✗ pyautogui 测试失败: {e}")
        return False

def test_screenshot():
    print("\n测试截图...")
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save("test_screenshot.png")
        print(f"✓ 截图成功，已保存到 test_screenshot.png")
        return True
    except Exception as e:
        print(f"✗ 截图失败: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 CAD AutoPilot 系统测试")
    print("=" * 60)
    
    results = []
    results.append(("导入测试", test_imports()))
    results.append(("pyautogui 测试", test_pyautogui()))
    results.append(("截图测试", test_screenshot()))
    
    print("\n" + "=" * 60)
    print("📊 测试结果:")
    print("=" * 60)
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")
    
    if all(r for _, r in results):
        print("\n🎉 所有测试通过！系统已就绪。")
    else:
        print("\n⚠️ 部分测试失败，请检查依赖安装。")
