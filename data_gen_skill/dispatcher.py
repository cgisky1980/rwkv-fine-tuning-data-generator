"""
任务调度器 — 创建、分发、管理数据生成任务

将 V4 的 DistributionConfig + Scheduler slots 转换为
可被多个 Agent 并发拉取的 work_items。
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, get_config
from .db import GenDatabase
from .models import (
    TaskStatus,
    WorkItemStatus,
    CreateTaskRequest,
    GenTask,
    WorkItem,
    SubmitResult,
    LanguageRatios,
)
from .schema_validator import validate, format_result


class GenTaskDispatcher:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or get_config()
        base_dir = Path(__file__).parent
        db_path = self.config.resolve_db_path(base_dir)
        self.db = GenDatabase(db_path)

    def create_task(self, request: CreateTaskRequest) -> GenTask:
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        task_name = f"{request.generator_type}_{request.count}items"
        now = datetime.now().isoformat()

        work_items = self._build_work_items(task_id, request)

        task = GenTask(
            task_id=task_id,
            name=task_name,
            generator_type=request.generator_type,
            status=TaskStatus.PENDING,
            request=request,
            total_items=len(work_items),
            completed_items=0,
            failed_items=0,
            created_at=now,
            updated_at=now,
        )

        self.db.create_task(task, work_items)
        self.db.update_task_status(task_id, TaskStatus.RUNNING)
        task.status = TaskStatus.RUNNING
        return task

    def _build_work_items(self, task_id: str, request: CreateTaskRequest) -> List[WorkItem]:
        lang_ratios = request.language_ratios or LanguageRatios()
        total = request.count

        lang_alloc = self._allocate_languages(lang_ratios, total)
        topics = self._load_topics(request.selected_topics)
        persona_types = self._get_persona_types()
        skills = self._load_skills()

        items = []
        slot_index = 0

        for lang, lang_count in lang_alloc.items():
            remaining = lang_count
            while remaining > 0:
                topic = topics[slot_index % len(topics)] if topics else "general"
                persona = persona_types[slot_index % len(persona_types)]
                skill = skills[slot_index % len(skills)] if skills else "weather_api"

                item = WorkItem(
                    item_id=f"{task_id}_w{slot_index:04d}",
                    task_id=task_id,
                    slot_index=slot_index,
                    language=lang,
                    persona=persona,
                    topic=topic,
                    skill=skill,
                )
                items.append(item)
                slot_index += 1
                remaining -= 1

        return items

    def _allocate_languages(self, ratios: LanguageRatios, total: int) -> Dict[str, int]:
        d = ratios.to_dict()
        raw = {k: total * v for k, v in d.items()}
        result = {k: int(v) for k, v in raw.items()}
        allocated = sum(result.values())
        remainder = total - allocated
        if remainder > 0:
            sorted_keys = sorted(raw.keys(), key=lambda k: raw[k] - int(raw[k]), reverse=True)
            for i in range(remainder):
                result[sorted_keys[i % len(sorted_keys)]] += 1
        return {k: v for k, v in result.items() if v > 0}

    def _load_topics(self, selected: Optional[List[str]]) -> List[str]:
        if selected:
            return selected
        topics_config = Path(__file__).parent.parent / "data" / "chat_topics.json"
        if topics_config.exists():
            try:
                with open(topics_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                topic_list = []
                for t in data.get("topics", []):
                    cat = t.get("category", "")
                    for level in t.get("levels", []):
                        topic_list.append(f"{cat}_{level}")
                return topic_list
            except Exception:
                pass
        return ["daily_chat_L1", "daily_chat_L2", "task_help_L1", "emotional_support_L1"]

    def _get_persona_types(self) -> List[str]:
        return [
            "tsundere", "gentle", "energetic", "cool", "dark",
            "sharp", "airhead", "chuuni", "yandere", "lazy",
            "genki", "intellectual", "mischievous", "loyal", "neutral",
        ]

    def _load_skills(self) -> List[str]:
        skills_config = Path(__file__).parent.parent / "data" / "skills_config.json"
        if skills_config.exists():
            try:
                with open(skills_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return [s.get("name", s.get("id", "")) for s in data.get("skills", data)]
            except Exception:
                pass
        return ["weather_api", "read_file", "write_file", "list_directory", "send_message"]

    def pull_work_items(self, agent_id: str, batch_size: Optional[int] = None) -> List[dict]:
        size = batch_size or self.config.batch_size
        items = self.db.pull_work_items(agent_id, size, self.config.work_item_timeout_seconds)
        return [item.to_dict() for item in items]

    def submit_result(
        self, agent_id: str, work_item_id: str, data: dict
    ) -> dict:
        item = self._get_work_item(work_item_id)
        if not item:
            return SubmitResult(
                success=False,
                work_item_id=work_item_id,
                agent_id=agent_id,
                message="Work item not found",
            ).to_dict()

        if item.agent_id != agent_id:
            return SubmitResult(
                success=False,
                work_item_id=work_item_id,
                agent_id=agent_id,
                message=f"Work item assigned to {item.agent_id}, not {agent_id}",
            ).to_dict()

        task = self.db.get_task(item.task_id)
        generator_type = task.generator_type if task else "clarify_skill"

        validation = validate(generator_type, data)
        if not validation.passed:
            self.db.mark_work_item_failed(
                work_item_id, agent_id, format_result(validation)
            )
            self.db.increment_agent_stats(agent_id, success=False)
            return SubmitResult(
                success=False,
                work_item_id=work_item_id,
                agent_id=agent_id,
                message="Validation failed",
                validation_errors=validation.errors,
            ).to_dict()

        ok, msg, record_count = self.db.submit_result(work_item_id, agent_id, data)
        self.db.increment_agent_stats(agent_id, success=True)

        return SubmitResult(
            success=ok,
            work_item_id=work_item_id,
            agent_id=agent_id,
            message=msg,
            record_count=record_count,
            validation_errors=validation.errors,
        ).to_dict()

    def _get_work_item(self, item_id: str) -> Optional[WorkItem]:
        with __import__("sqlite3").connect(self.db.db_path) as conn:
            row = conn.execute(
                """SELECT item_id, task_id, slot_index, language, persona, topic, skill,
                   status, agent_id, assigned_at, submitted_at, error_message, retry_count
                   FROM work_items WHERE item_id = ?""",
                (item_id,),
            ).fetchone()
        if row:
            return GenDatabase._row_to_work_item(row)
        return None

    def get_task(self, task_id: str) -> Optional[dict]:
        task = self.db.get_task(task_id)
        if task:
            return task.to_dict()
        return None

    def list_tasks(self, status_filter: Optional[str] = None, limit: int = 50) -> List[dict]:
        tasks = self.db.list_tasks(status_filter, limit)
        return [t.to_dict() for t in tasks]

    def cancel_task(self, task_id: str) -> bool:
        return self.db.cancel_task(task_id)

    def get_task_records(self, task_id: str, limit: int = 1000) -> List[dict]:
        return self.db.get_task_records(task_id, limit)

    def export_rwkv(self, task_id: str, output_path: Optional[str] = None) -> dict:
        records = self.db.get_task_records(task_id)
        if not records:
            return {"success": False, "error": "No records found for this task"}

        if output_path is None:
            export_dir = Path(__file__).parent.parent / "data" / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(
                export_dir / f"rwkv_export_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
            )

        try:
            from pipeline.export_template import export_rwkv_data
        except ImportError:
            return {
                "success": False,
                "error": "Cannot import pipeline.export_template. Ensure sys.path includes V4 root.",
            }

        temp_file = Path(output_path).parent / f"_temp_{Path(output_path).name}"
        temp_data_file = Path(output_path).parent / f"_temp_data_{Path(output_path).stem}.jsonl"

        with open(temp_data_file, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        total = export_rwkv_data(str(temp_data_file), str(temp_file))

        Path(temp_file).rename(output_path)
        temp_data_file.unlink(missing_ok=True)

        return {
            "success": True,
            "output_file": output_path,
            "records_count": total,
        }

    def get_stats(self) -> dict:
        return self.db.get_stats()


_dispatcher: Optional[GenTaskDispatcher] = None


def get_dispatcher(config_path: Optional[str] = None) -> GenTaskDispatcher:
    global _dispatcher
    if _dispatcher is None:
        cfg = get_config(config_path)
        _dispatcher = GenTaskDispatcher(cfg)
    return _dispatcher