"""
独立数据生成 Skill — 数据模型
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkItemStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    VALIDATED = "validated"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass
class LanguageRatios:
    zh: float = 0.50
    en: float = 0.20
    ja: float = 0.05
    ko: float = 0.05
    de: float = 0.05
    fr: float = 0.05
    es: float = 0.05
    ru: float = 0.05

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LanguageRatios":
        if not data:
            return cls()
        defaults = {f.name: f.default for f in cls.__dataclass_fields__.values()}
        merged = {**defaults, **data}
        return cls(**{k: merged.get(k, defaults[k]) for k in defaults})


@dataclass
class CreateTaskRequest:
    generator_type: str = "clarify_skill"
    count: int = 100
    language_ratios: Optional[LanguageRatios] = None
    temperature: float = 0.7
    concurrency: int = 4
    selected_topics: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.language_ratios:
            d["language_ratios"] = self.language_ratios.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreateTaskRequest":
        lang = None
        if data.get("language_ratios"):
            lang = LanguageRatios.from_dict(data["language_ratios"])
        return cls(
            generator_type=data.get("generator_type", "clarify_skill"),
            count=data.get("count", 100),
            language_ratios=lang,
            temperature=data.get("temperature", 0.7),
            concurrency=data.get("concurrency", 4),
            selected_topics=data.get("selected_topics"),
        )


@dataclass
class GenTask:
    task_id: str
    name: str
    generator_type: str
    status: TaskStatus
    request: CreateTaskRequest
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    created_at: str = ""
    updated_at: str = ""

    @property
    def progress(self) -> float:
        if self.total_items == 0:
            return 0.0
        return self.completed_items / self.total_items

    @property
    def is_complete(self) -> bool:
        return self.completed_items + self.failed_items >= self.total_items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "generator_type": self.generator_type,
            "status": self.status.value,
            "request": self.request.to_dict(),
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "failed_items": self.failed_items,
            "progress": round(self.progress, 4),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class WorkItem:
    item_id: str
    task_id: str
    slot_index: int
    language: str
    persona: str
    topic: str
    skill: str
    status: WorkItemStatus = WorkItemStatus.PENDING
    agent_id: Optional[str] = None
    assigned_at: Optional[str] = None
    submitted_at: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkItem":
        return cls(
            item_id=data["item_id"],
            task_id=data["task_id"],
            slot_index=data.get("slot_index", 0),
            language=data["language"],
            persona=data.get("persona", ""),
            topic=data.get("topic", ""),
            skill=data.get("skill", ""),
            status=WorkItemStatus(data.get("status", "pending")),
            agent_id=data.get("agent_id"),
            assigned_at=data.get("assigned_at"),
            submitted_at=data.get("submitted_at"),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
        )


@dataclass
class SubmitResult:
    success: bool
    work_item_id: str
    agent_id: str
    message: str = ""
    record_count: int = 0
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentInfo:
    agent_id: str
    last_seen: str = ""
    items_processed: int = 0
    items_failed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)