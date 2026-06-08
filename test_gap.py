"""Quick gap test"""
from tools.registry import ToolRegistry
from tools.builtin import register_builtins

r = ToolRegistry()
register_builtins(r)
print(f"Tools: {len(r.tools)}")
for name in sorted(r.tools.keys()):
    print(f"  {name}")
