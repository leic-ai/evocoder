# 🔧 CAD AutoPilot — 视觉驱动 CAD 自动化系统

## 概述

让 AI 能够像人类一样"看屏幕"并操作 CAD 软件。使用 MiMo v2.5 多模态推理模型作为"眼睛"，结合 GUI 自动化实现 CAD 建模。

## 架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  MiMo v2.5  │ ←── │ VisionEngine │ ←── │ CADController│
│  (视觉AI)    │     │ (视觉分析)    │     │ (GUI操作)    │
└─────────────┘     └──────────────┘     └─────────────┘
                           ↑                    ↑
                           │                    │
                      ┌────┴────┐          ┌────┴────┐
                      │  截屏    │          │ pyautogui│
                      │  PIL    │          │ 键盘/鼠标 │
                      └─────────┘          └─────────┘
```

## 快速开始

```python
from superpowers.cad_autopilot import CADAutoPilot

# 初始化（使用默认 API Key）
autopilot = CADAutoPilot()

# 查看当前屏幕
state = autopilot.see()
print(state)

# 让 AI 自动执行任务
autopilot.execute("在绘图区域画一个矩形")
```

## API 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MIMO_API_KEY` | `sk-coyrt3...` | MiMo API 密钥 |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | API 地址 |
| `MIMO_MODEL` | `mimo-v2.5` | 视觉模型名称 |

> ⚠️ **注意**：使用 `mimo-v2.5`（不是 `mimo-v2.5-pro`），只有前者支持图片输入。

## 核心组件

### VisionEngine (`vision_engine.py`)

多模态视觉分析引擎，负责：
- 屏幕截图
- 图片编码
- MiMo API 调用
- 推理模型输出解析

```python
from superpowers.vision_engine import VisionEngine

engine = VisionEngine()

# 分析图片
result = engine.analyze_image(base64_image, "描述这张图片")

# 分析屏幕
result = engine.analyze_screen("当前打开了什么软件？")

# 查找 UI 元素
pos = engine.find_element("File 菜单")  # 返回 (x, y)
```

### CADController (`cad_controller.py`)

GUI 自动化控制器，负责：
- 鼠标点击、拖拽
- 键盘输入、快捷键
- 命令执行
- 操作历史记录

### CADAutoPilot (`cad_autopilot.py`)

一键式接口，整合视觉引擎和控制器：
- `see()` — 分析当前屏幕
- `find(description)` — 查找 UI 元素
- `click(description)` — 点击元素
- `execute(task)` — AI 自动执行任务
- `draw_line/circle/rect()` — 绘制图形

## 使用示例

### 基础操作
```python
autopilot = CADAutoPilot()

# 查看屏幕
state = autopilot.see()

# 点击工具
autopilot.click("直线工具")

# 绘制
autopilot.draw_line((100, 100), (300, 200))
```

### AI 自动执行
```python
autopilot = CADAutoPilot()

# 自然语言描述任务
autopilot.execute("画一个边长为 200 的正方形")
autopilot.execute("在正方形中心画一个内切圆")
autopilot.execute("标注圆的直径")
```

## 依赖

```
openai>=1.0.0
Pillow>=10.0.0
pyautogui>=0.9.54
pyperclip>=1.8.0
```

安装：
```bash
pip install openai Pillow pyautogui pyperclip
```

## 技术细节

### MiMo v2.5 推理模型

- 支持图片输入（视觉能力）
- 输出格式：推理过程在 `reasoning_content` 字段，最终答案在 `content` 字段
- VisionEngine 自动处理两种输出格式

### 安全机制

- pyautogui FAILSAFE：鼠标移到屏幕左上角可紧急停止
- 操作间隔：每个 GUI 操作间有 0.1 秒延迟
- 截图保存：所有操作前的截图保存到 `cad_screenshots/` 目录

## 文件结构

```
superpowers/
├── vision_engine.py      # 视觉分析引擎
├── cad_controller.py     # GUI 自动化控制器
├── cad_autopilot.py      # 一键式接口
├── cad_examples.py       # 使用示例
├── test_cad.py           # 单元测试
├── CAD_README.md         # 本文档
└── README.md             # 简要说明
```
