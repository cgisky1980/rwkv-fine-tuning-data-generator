"""
V4 数据生成 Skill 服务

提供统一的数据生成接口，支持：
- 需求澄清+技能调用场景的数据生成
- 基于指纹的去重机制，避免生成重复数据
- RWKV 训练数据导出
- 可被其他 Agent 调用的清晰接口
"""

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .task_manager import (
    TaskManager,
    TaskConfig,
    TaskStatus,
    get_task_manager,
)
from .generators import get_generator_loader


@dataclass
class GenRequest:
    generator_type: str = "clarify_skill"
    count: int = 10
    temperature: float = 0.7
    seed: Optional[int] = None
    concurrency: int = 4
    language: str = "zh"
    topic: Optional[str] = None
    user_profile_ratio: float = 0.3
    provider_id: Optional[str] = None
    max_tokens: int = 8192
    skip_duplicate: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenRequest":
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


@dataclass
class GenResult:
    success: bool
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    records_generated: int = 0
    records_failed: int = 0
    is_duplicate: bool = False
    duplicate_task_id: Optional[str] = None
    error_message: Optional[str] = None
    data_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExportResult:
    success: bool
    output_file: Optional[str] = None
    records_count: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DataGenSkill:
    """数据生成 Skill 服务 - 统一的数据生成与去重接口"""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "data"
        self.db_path = self.data_dir / "tasks.db"
        self.task_manager = get_task_manager()
        self._init_fingerprints_table()
        self._lock = threading.Lock()

    def _init_fingerprints_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gen_fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL,
                    generator_type TEXT NOT NULL,
                    language TEXT NOT NULL,
                    topic TEXT,
                    skills_hash TEXT,
                    record_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_gen_fingerprints_fp
                ON gen_fingerprints(fingerprint)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_gen_fingerprints_gen_type
                ON gen_fingerprints(generator_type)
            """)
            conn.commit()

    def compute_fingerprint(self, request: GenRequest) -> str:
        parts = [
            request.generator_type,
            request.language,
            str(request.topic or ""),
            str(request.count),
            str(request.temperature),
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def check_duplicate(self, request: GenRequest) -> Optional[Dict[str, Any]]:
        fingerprint = self.compute_fingerprint(request)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT fingerprint, task_id, generator_type, language, topic, record_count, created_at FROM gen_fingerprints WHERE fingerprint = ?",
                (fingerprint,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "fingerprint": row[0],
                    "task_id": row[1],
                    "generator_type": row[2],
                    "language": row[3],
                    "topic": row[4],
                    "record_count": row[5],
                    "created_at": row[6],
                }
        return None

    def _record_fingerprint(self, request: GenRequest, task_id: str, record_count: int = 0):
        fingerprint = self.compute_fingerprint(request)
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """INSERT INTO gen_fingerprints (fingerprint, task_id, generator_type, language, topic, skills_hash, record_count, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        fingerprint,
                        task_id,
                        request.generator_type,
                        request.language,
                        request.topic or "",
                        "",
                        record_count,
                        now,
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    def generate(self, request: GenRequest) -> GenResult:
        if request.skip_duplicate:
            existing = self.check_duplicate(request)
            if existing:
                task = self.task_manager.get_task(existing["task_id"])
                if task and task.status == TaskStatus.COMPLETED:
                    return GenResult(
                        success=True,
                        task_id=existing["task_id"],
                        is_duplicate=True,
                        duplicate_task_id=existing["task_id"],
                        records_generated=existing["record_count"],
                        data_file=task.data_file if task else None,
                    )

        loader = get_generator_loader()
        available = loader.list_generators()
        generator_ids = [g["id"] for g in available]
        if request.generator_type not in generator_ids:
            return GenResult(
                success=False,
                error_message=f"Generator not found: {request.generator_type}. Available: {generator_ids}",
            )

        task_name = (
            f"{request.generator_type}_{request.language}"
            f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        config = TaskConfig(
            generator_type=request.generator_type,
            count=request.count,
            temperature=request.temperature,
            seed=request.seed,
            concurrency=request.concurrency,
            user_profile_ratio=request.user_profile_ratio,
            provider_id=request.provider_id,
            max_tokens=request.max_tokens,
        )

        try:
            task = self.task_manager.create_task(task_name, config)
        except ValueError as e:
            return GenResult(
                success=False,
                error_message=str(e),
            )

        self._record_fingerprint(request, task.id, record_count=0)

        from .task_processor import get_task_processor

        processor = get_task_processor(max_workers=request.concurrency)
        processor.submit_task(task.id)

        return GenResult(
            success=True,
            task_id=task.id,
            task_name=task_name,
            data_file=task.data_file,
        )

    def generate_sync(self, request: GenRequest, timeout: float = 300.0) -> GenResult:
        result = self.generate(request)
        if not result.success or result.is_duplicate:
            return result

        task_id = result.task_id
        start_time = datetime.now()

        while True:
            task = self.task_manager.get_task(task_id)
            if not task:
                return GenResult(
                    success=False,
                    task_id=task_id,
                    error_message="Task not found after creation",
                )

            if task.status == TaskStatus.COMPLETED:
                self._update_fingerprint_count(task_id, task.stats.records_generated)
                return GenResult(
                    success=True,
                    task_id=task_id,
                    task_name=result.task_name,
                    records_generated=task.stats.records_generated,
                    records_failed=task.stats.records_failed,
                    data_file=task.data_file,
                )

            if task.status == TaskStatus.FAILED:
                return GenResult(
                    success=False,
                    task_id=task_id,
                    task_name=result.task_name,
                    error_message=task.error_message or "Task failed",
                )

            if task.status == TaskStatus.CANCELLED:
                return GenResult(
                    success=False,
                    task_id=task_id,
                    task_name=result.task_name,
                    error_message="Task was cancelled",
                )

            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                return GenResult(
                    success=False,
                    task_id=task_id,
                    task_name=result.task_name,
                    records_generated=task.stats.records_generated,
                    error_message=f"Timeout after {timeout}s",
                )

            import time
            time.sleep(2)

    def _update_fingerprint_count(self, task_id: str, count: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE gen_fingerprints SET record_count = ? WHERE task_id = ?",
                (count, task_id),
            )
            conn.commit()

    def export_rwkv(
        self,
        task_ids: List[str],
        output_path: Optional[str] = None,
    ) -> ExportResult:
        from .export_template import export_rwkv_data

        if not task_ids:
            return ExportResult(success=False, error_message="No task IDs provided")

        tasks_data_files = []
        for tid in task_ids:
            task = self.task_manager.get_task(tid)
            if not task:
                return ExportResult(
                    success=False, error_message=f"Task not found: {tid}"
                )
            if task.status != TaskStatus.COMPLETED:
                return ExportResult(
                    success=False,
                    error_message=f"Task {tid} not completed (status: {task.status.value})",
                )
            if not Path(task.data_file).exists():
                return ExportResult(
                    success=False,
                    error_message=f"Data file not found for task {tid}: {task.data_file}",
                )
            tasks_data_files.append(task.data_file)

        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = self.data_dir / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(export_dir / f"rwkv_export_{timestamp}.jsonl")

        total_records = 0
        try:
            for data_file in tasks_data_files:
                count = export_rwkv_data(data_file, output_path)
                total_records += count

            for tid in task_ids:
                self.task_manager.update_export_status(tid, "exported")
            self.task_manager.mark_tasks_exported(
                task_ids, output_path, "rwkv_jsonl", total_records
            )

            return ExportResult(
                success=True,
                output_file=output_path,
                records_count=total_records,
            )
        except Exception as e:
            return ExportResult(
                success=False,
                error_message=f"Export failed: {str(e)}",
            )

    def list_generated(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        filters = filters or {}
        query = "SELECT fingerprint, task_id, generator_type, language, topic, record_count, created_at FROM gen_fingerprints WHERE 1=1"
        params: list = []

        if "generator_type" in filters:
            query += " AND generator_type = ?"
            params.append(filters["generator_type"])
        if "language" in filters:
            query += " AND language = ?"
            params.append(filters["language"])
        if "topic" in filters:
            query += " AND topic = ?"
            params.append(filters["topic"])

        query += " ORDER BY created_at DESC"

        if "limit" in filters:
            query += " LIMIT ?"
            params.append(int(filters["limit"]))

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        return [
            {
                "fingerprint": row[0],
                "task_id": row[1],
                "generator_type": row[2],
                "language": row[3],
                "topic": row[4],
                "record_count": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def get_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT generator_type, COUNT(*), SUM(record_count)
                FROM gen_fingerprints
                GROUP BY generator_type
            """)
            by_type = {
                row[0]: {"tasks": row[1], "records": row[2] or 0}
                for row in cursor.fetchall()
            }

            cursor = conn.execute("SELECT COUNT(*) FROM gen_fingerprints")
            total_fingerprints = cursor.fetchone()[0]

            cursor = conn.execute("SELECT SUM(record_count) FROM gen_fingerprints")
            total_records = cursor.fetchone()[0] or 0

            cursor = conn.execute("""
                SELECT language, COUNT(*), SUM(record_count)
                FROM gen_fingerprints
                GROUP BY language
            """)
            by_language = {
                row[0]: {"tasks": row[1], "records": row[2] or 0}
                for row in cursor.fetchall()
            }

        return {
            "total_fingerprints": total_fingerprints,
            "total_records": total_records,
            "by_generator_type": by_type,
            "by_language": by_language,
        }

    def delete_fingerprint(self, fingerprint: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM gen_fingerprints WHERE fingerprint = ?",
                (fingerprint,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def clear_fingerprints(self, generator_type: Optional[str] = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            if generator_type:
                cursor = conn.execute(
                    "DELETE FROM gen_fingerprints WHERE generator_type = ?",
                    (generator_type,),
                )
            else:
                cursor = conn.execute("DELETE FROM gen_fingerprints")
            conn.commit()
            return cursor.rowcount


_skill_instance: Optional[DataGenSkill] = None


def get_data_gen_skill() -> DataGenSkill:
    global _skill_instance
    if _skill_instance is None:
        _skill_instance = DataGenSkill()
    return _skill_instance
