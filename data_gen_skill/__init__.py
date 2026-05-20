"""
独立数据生成 Skill 系统

提供基于 MCP 协议的分布式数据生成能力：
- Agent 通过 MCP 工具创建生成任务
- Dispatcher 将任务拆分为原子工作项
- 多个 Agent 并行拉取工作项、自行生成数据、提交结果
- 系统负责校验和存储，不调用外部 AI API
"""

from .models import (
    TaskStatus,
    WorkItemStatus,
    CreateTaskRequest,
    UpdateTaskRequest,
    GenTask,
    WorkItem,
    SubmitResult,
    GeneratorInfo,
    AgentInfo,
    LanguageRatios,
)

from .config import Config, get_config

__all__ = [
    "TaskStatus",
    "WorkItemStatus",
    "CreateTaskRequest",
    "GenTask",
    "WorkItem",
    "SubmitResult",
    "AgentInfo",
    "LanguageRatios",
    "Config",
    "get_config",
]