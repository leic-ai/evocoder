"""SDD Flow — 需求驱动开发流程

借鉴 DeepSeek GUI 的 SDD 流程：
需求草稿 → AI补全 → 生成计划 → 执行
"""

import json
import time
from pathlib import Path
from openai import OpenAI


REQUIREMENT_COMPLETION_PROMPT = """你是一个需求分析师。用户写了一个需求草稿，请帮他补全和完善。

## 用户草稿
{draft}

## 项目上下文
{context}

请输出 JSON 格式：
```json
{{
  "title": "需求标题",
  "background": "背景说明",
  "goals": ["目标1", "目标2"],
  "acceptance_criteria": ["验收标准1", "验收标准2"],
  "technical_notes": "技术备注",
  "questions": ["需要澄清的问题1", "问题2"]
}}
```
"""

PLAN_GENERATION_PROMPT = """你是一个技术架构师。根据需求，生成详细的实施计划。

## 需求
{requirement}

## 项目结构
{project_structure}

请输出 JSON 格式：
```json
{{
  "plan_title": "计划标题",
  "architecture": "架构说明",
  "tasks": [
    {{
      "id": 1,
      "title": "任务标题",
      "description": "任务描述",
      "files": ["涉及文件1", "文件2"],
      "steps": ["步骤1", "步骤2"],
      "test": "测试方法"
    }}
  ],
  "dependencies": ["依赖1", "依赖2"],
  "risks": ["风险1", "风险2"]
}}
```
"""


class SDDFlow:
    """SDD 需求驱动开发流程"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-v4-pro", workspace: str = ".evocoder"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.workspace = Path(workspace)
        self.sdd_dir = self.workspace / "sdd"
        self.sdd_dir.mkdir(parents=True, exist_ok=True)
        self.requirements_dir = self.sdd_dir / "requirements"
        self.plans_dir = self.sdd_dir / "plans"
        self.requirements_dir.mkdir(exist_ok=True)
        self.plans_dir.mkdir(exist_ok=True)

    def create_draft(self, draft: str, context: str = "") -> dict:
        draft_id = f"draft_{int(time.time())}"
        draft_data = {
            "id": draft_id,
            "draft": draft,
            "context": context,
            "created_at": time.time(),
            "status": "draft",
        }
        draft_path = self.requirements_dir / f"{draft_id}.json"
        draft_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return draft_data

    def complete_requirement(self, draft_id: str) -> dict:
        draft_path = self.requirements_dir / f"{draft_id}.json"
        if not draft_path.exists():
            return {"error": f"Draft not found: {draft_id}"}
        draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
        prompt = REQUIREMENT_COMPLETION_PROMPT.format(
            draft=draft_data["draft"],
            context=draft_data.get("context", "无"),
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            draft_data.update(result)
            draft_data["status"] = "completed"
            draft_data["completed_at"] = time.time()
            draft_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2), encoding="utf-8")
            return draft_data
        except Exception as e:
            return {"error": f"AI completion failed: {e}"}

    def generate_plan(self, draft_id: str, project_structure: str = "") -> dict:
        draft_path = self.requirements_dir / f"{draft_id}.json"
        if not draft_path.exists():
            return {"error": f"Requirement not found: {draft_id}"}
        requirement = json.loads(draft_path.read_text(encoding="utf-8"))
        prompt = PLAN_GENERATION_PROMPT.format(
            requirement=json.dumps(requirement, ensure_ascii=False, indent=2),
            project_structure=project_structure or "未提供",
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            plan_id = f"plan_{int(time.time())}"
            plan_data = {
                "id": plan_id,
                "requirement_id": draft_id,
                "plan": result,
                "created_at": time.time(),
                "status": "pending",
            }
            plan_path = self.plans_dir / f"{plan_id}.json"
            plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
            requirement["plan_id"] = plan_id
            requirement["status"] = "planned"
            draft_path.write_text(json.dumps(requirement, ensure_ascii=False, indent=2), encoding="utf-8")
            return plan_data
        except Exception as e:
            return {"error": f"Plan generation failed: {e}"}

    def list_requirements(self) -> list[dict]:
        requirements = []
        for path in self.requirements_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                requirements.append({
                    "id": data["id"],
                    "title": data.get("title", "未命名"),
                    "status": data["status"],
                    "created_at": data["created_at"],
                })
            except Exception:
                continue
        return requirements

    def list_plans(self) -> list[dict]:
        plans = []
        for path in self.plans_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                plans.append({
                    "id": data["id"],
                    "requirement_id": data["requirement_id"],
                    "status": data["status"],
                    "created_at": data["created_at"],
                })
            except Exception:
                continue
        return plans

    def get_requirement(self, draft_id: str) -> dict | None:
        draft_path = self.requirements_dir / f"{draft_id}.json"
        if not draft_path.exists():
            return None
        return json.loads(draft_path.read_text(encoding="utf-8"))

    def get_plan(self, plan_id: str) -> dict | None:
        plan_path = self.plans_dir / f"{plan_id}.json"
        if not plan_path.exists():
            return None
        return json.loads(plan_path.read_text(encoding="utf-8"))

    def update_task_status(self, plan_id: str, task_id: int, status: str) -> bool:
        plan_path = self.plans_dir / f"{plan_id}.json"
        if not plan_path.exists():
            return False
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
        tasks = plan_data.get("plan", {}).get("tasks", [])
        for task in tasks:
            if task["id"] == task_id:
                task["status"] = status
                plan_path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
                return True
        return False
