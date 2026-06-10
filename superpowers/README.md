# Superpowers — CAD AutoPilot

视觉驱动的 CAD 自动化系统。

使用 MiMo v2.5 多模态推理模型 + GUI 自动化，让 AI 能够"看屏幕"并操作 CAD 软件。

## 快速开始

```python
from superpowers.cad_autopilot import CADAutoPilot

autopilot = CADAutoPilot()
autopilot.see()       # 看屏幕
autopilot.execute("画一个矩形")  # AI 自动执行
```

详细文档见 [CAD_README.md](CAD_README.md)
