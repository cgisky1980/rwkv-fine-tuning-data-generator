"""
MCP Server — 数据生成 Skill 工具端点

将 GenTaskDispatcher 的方法暴露为 MCP 工具，
Agent（如 SOLO）通过 MCP 协议调用来创建、拉取、提交数据生成任务。

启动方式:
  python -m data_gen_skill.mcp_server
  python -m data_gen_skill.mcp_server --config data_gen_skill/config.yaml

MCP 配置:
  {
    "mcpServers": {
      "data-gen-skill": {
        "command": "python",
        "args": ["-m", "data_gen_skill.mcp_server"],
        "cwd": "${workspaceFolder}/V4"
      }
    }
  }
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import mcp.server.stdio
    import mcp.types as types
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationCapabilities

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def tool(name: str, description: str, schema: dict):
    """Decorate a function as an MCP tool"""
    def decorator(fn):
        fn._mcp_tool_name = name
        fn._mcp_tool_description = description
        fn._mcp_tool_schema = schema
        return fn
    return decorator


class DataGenSkillMCP:
    def __init__(self, config_path: str = None):
        from .dispatcher import get_dispatcher, GenTaskDispatcher

        if config_path:
            from .config import Config
            self.dispatcher = GenTaskDispatcher(Config(config_path))
        else:
            self.dispatcher = get_dispatcher()

    @tool(
        name="create_gen_task",
        description="Create a new data generation task. Breaks the task into atomic work items that agents can pull.",
        schema={
            "type": "object",
            "properties": {
                "generator_type": {
                    "type": "string",
                    "description": "Generator type: clarify_skill, single_skill, mixed_dialog, complex_skill, no_tool",
                    "default": "clarify_skill",
                },
                "count": {
                    "type": "integer",
                    "description": "Total number of data records to generate",
                    "default": 100,
                },
                "language_ratios": {
                    "type": "object",
                    "description": "Language distribution ratios (zh, en, ja, ko, de, fr, es, ru). Sum should be ~1.0",
                },
                "temperature": {
                    "type": "number",
                    "description": "LLM temperature for generation",
                    "default": 0.7,
                },
                "concurrency": {
                    "type": "integer",
                    "description": "Max concurrent agents for this task",
                    "default": 4,
                },
                "selected_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific topic categories to include (empty = all)",
                },
            },
            "required": ["generator_type", "count"],
        },
    )
    async def create_gen_task(self, **kwargs) -> list[types.TextContent]:
        from .models import CreateTaskRequest, LanguageRatios

        req = CreateTaskRequest(
            generator_type=kwargs.get("generator_type", "clarify_skill"),
            count=int(kwargs.get("count", 100)),
            language_ratios=LanguageRatios.from_dict(kwargs.get("language_ratios", {})),
            temperature=float(kwargs.get("temperature", 0.7)),
            concurrency=int(kwargs.get("concurrency", 4)),
            selected_topics=kwargs.get("selected_topics"),
        )

        task = self.dispatcher.create_task(req)
        result = {
            "success": True,
            "task": task.to_dict(),
        }
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    @tool(
        name="list_gen_tasks",
        description="List all data generation tasks with optional status filter.",
        schema={
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "description": "Filter by status: pending, running, completed, failed, cancelled",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max tasks to return",
                    "default": 50,
                },
            },
        },
    )
    async def list_gen_tasks(self, **kwargs) -> list[types.TextContent]:
        status = kwargs.get("status_filter")
        limit = int(kwargs.get("limit", 50))
        tasks = self.dispatcher.list_tasks(status, limit)
        result = {"success": True, "count": len(tasks), "tasks": tasks}
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    @tool(
        name="get_gen_task",
        description="Get detailed status of a specific generation task.",
        schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID",
                },
            },
            "required": ["task_id"],
        },
    )
    async def get_gen_task(self, task_id: str) -> list[types.TextContent]:
        task = self.dispatcher.get_task(task_id)
        if task is None:
            return [types.TextContent(type="text", text=json.dumps({"success": False, "error": "Task not found"}, ensure_ascii=False))]
        return [types.TextContent(type="text", text=json.dumps({"success": True, "task": task}, ensure_ascii=False, indent=2))]

    @tool(
        name="cancel_gen_task",
        description="Cancel a running or pending generation task.",
        schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to cancel",
                },
            },
            "required": ["task_id"],
        },
    )
    async def cancel_gen_task(self, task_id: str) -> list[types.TextContent]:
        ok = self.dispatcher.cancel_task(task_id)
        return [types.TextContent(type="text", text=json.dumps({"success": ok, "message": "Cancelled" if ok else "Task not found or already completed"}, ensure_ascii=False))]

    @tool(
        name="pull_work_items",
        description="Agent pulls work items for generation. Returns assigned atomic work items. The agent must call submit_work_result after generating data.",
        schema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Unique agent identifier",
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Number of work items to pull",
                    "default": 5,
                },
            },
            "required": ["agent_id"],
        },
    )
    async def pull_work_items(self, agent_id: str, batch_size: int = 5) -> list[types.TextContent]:
        items = self.dispatcher.pull_work_items(agent_id, int(batch_size))
        result = {
            "success": True,
            "count": len(items),
            "items": items,
            "message": "No work available" if not items else f"Assigned {len(items)} items",
        }
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    @tool(
        name="submit_work_result",
        description="Agent submits generated data for a work item. Data will be validated against the generator schema before storage.",
        schema={
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent identifier (must match the agent that pulled this item)",
                },
                "work_item_id": {
                    "type": "string",
                    "description": "Work item ID returned by pull_work_items",
                },
                "data": {
                    "type": "object",
                    "description": "Generated data conforming to the generator's output schema",
                },
            },
            "required": ["agent_id", "work_item_id", "data"],
        },
    )
    async def submit_work_result(self, agent_id: str, work_item_id: str, data: dict) -> list[types.TextContent]:
        result = self.dispatcher.submit_result(agent_id, work_item_id, data)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    @tool(
        name="get_system_stats",
        description="Get overall system statistics for the data generation skill.",
        schema={
            "type": "object",
            "properties": {},
        },
    )
    async def get_system_stats(self) -> list[types.TextContent]:
        stats = self.dispatcher.get_stats()
        return [types.TextContent(type="text", text=json.dumps({"success": True, "stats": stats}, ensure_ascii=False, indent=2))]

    @tool(
        name="export_rwkv",
        description="Export generated data for a task to RWKV training format.",
        schema={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "Task ID to export",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output file path (auto-generated if not specified)",
                },
            },
            "required": ["task_id"],
        },
    )
    async def export_rwkv(self, task_id: str, output_path: str = None) -> list[types.TextContent]:
        result = self.dispatcher.export_rwkv(task_id, output_path)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


def _collect_tools(instance: DataGenSkillMCP) -> list:
    tools = []
    for name in dir(instance):
        fn = getattr(instance, name)
        if callable(fn) and hasattr(fn, "_mcp_tool_name"):
            tools.append(
                types.Tool(
                    name=fn._mcp_tool_name,
                    description=fn._mcp_tool_description,
                    inputSchema=fn._mcp_tool_schema,
                )
            )
    return tools


def _get_handler(instance: DataGenSkillMCP, tool_name: str):
    for name in dir(instance):
        fn = getattr(instance, name)
        if callable(fn) and hasattr(fn, "_mcp_tool_name") and fn._mcp_tool_name == tool_name:
            return fn
    return None


def main():
    parser = argparse.ArgumentParser(description="Data Gen Skill MCP Server")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    if not HAS_MCP:
        print("ERROR: mcp package not installed. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    skill = DataGenSkillMCP(args.config)
    server = Server("data-gen-skill")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return _collect_tools(skill)

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _get_handler(skill, name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        return await handler(**arguments)

    async def run():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationCapabilities(
                    sampling=None,
                    experimental=None,
                    roots=None,
                ),
            )

    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()