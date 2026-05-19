# 数据生成 Skill 系统 参考文档

## 概述

`data_gen_skill/` 是 V4 项目内的**独立子系统**，提供基于 MCP 协议的分布式数据生成能力：

- **MCP 工具入口**：Agent（如 SOLO）通过 MCP 协议调用 `create_gen_task`、`pull_work_items`、`submit_work_result` 等工具
- **调度器分发**：`Dispatcher` 将任务拆分为原子 `work_items`，多 Agent 并发拉取（SQLite 行锁保证不冲突）
- **Agent 自备 LLM**：系统不调用外部 AI API，只做调度、校验、存储
- **合规校验**：`SchemaValidator` 验证 Agent 提交的数据是否符合生成器规范
- **去重机制**：基于 `item_id + data` 的 SHA256 指纹，避免重复入库
- **独立数据库**：`data/gen_data.db` 不与 V4 的 `tasks.db` 混用

## 系统流程

```
SOLO Agent ──MCP工具──▶ MCP Server ──create_task()──▶ Dispatcher
                                                        │ 拆分 slots
                                                        ▼
                                                work_items (DB队列)
                                                  ↙         ↘
                                           Agent A        Agent B
                                           (LLM生成)      (LLM生成)
                                              ↘            ↙
                                          Schema Validator
                                                │
                                          gen_data.db
```

## 目录结构

```
data_gen_skill/
├── __init__.py           # 包入口
├── models.py             # 数据模型 (GenTask, WorkItem, ...)
├── config.py             # 配置管理
├── config.yaml           # 默认配置
├── db.py                 # SQLite 数据库 (gen_data.db)
├── dispatcher.py         # 任务调度器
├── schema_validator.py   # 合规校验器
├── worker.py             # Agent 参考实现 (MockAgentWorker)
├── mcp_server.py         # MCP 工具端点
└── data/                 # 运行时自动创建 gen_data.db
```

## 核心类

### GenTaskDispatcher

```python
from data_gen_skill.dispatcher import GenTaskDispatcher
from data_gen_skill.models import CreateTaskRequest

d = GenTaskDispatcher()

# 创建任务
req = CreateTaskRequest(generator_type="clarify_skill", count=100)
task = d.create_task(req)

# Agent 拉取工作
items = d.pull_work_items("my_agent", batch_size=5)

# Agent 提交结果
result = d.submit_result("my_agent", item["item_id"], generated_data)

# 查询/导出
d.get_task(task_id)
d.list_tasks(status_filter="running")
d.export_rwkv(task_id)
d.get_stats()
```

### GenAgentWorker

```python
from data_gen_skill.worker import GenAgentWorker

class MyAgent(GenAgentWorker):
    def generate_for_item(self, item: dict) -> dict:
        # 用自己的 LLM 生成符合 schema 的数据
        # ...
        return data

worker = MyAgent("my_agent_id", dispatcher)
worker.run_loop(batch_size=3)
```

### MCP Server

启动：
```bash
cd V4
python -m data_gen_skill.mcp_server
python -m data_gen_skill.mcp_server --config data_gen_skill/config.yaml
```

MCP 配置（mcp.json）：
```json
{
  "mcpServers": {
    "data-gen-skill": {
      "command": "python",
      "args": ["-m", "data_gen_skill.mcp_server"],
      "cwd": "${workspaceFolder}/V4"
    }
  }
}
```

### MCP 工具列表

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `create_gen_task` | generator_type, count, language_ratios, ... | 创建新生成任务 |
| `list_gen_tasks` | status_filter, limit | 列出所有任务 |
| `get_gen_task` | task_id | 查看任务详情和进度 |
| `cancel_gen_task` | task_id | 取消任务 |
| `pull_work_items` | agent_id, batch_size | Agent 拉取工作项 |
| `submit_work_result` | agent_id, work_item_id, data | Agent 提交结果 |
| `get_system_stats` | — | 系统统计 |
| `export_rwkv` | task_id, output_path | 导出 RWKV 格式 |

## 数据库表

### gen_tasks

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | TEXT | 主键 |
| name | TEXT | 任务名称 |
| generator_type | TEXT | 生成器类型 |
| status | TEXT | pending/running/completed/failed/cancelled |
| request_json | TEXT | 请求参数 JSON |
| total_items | INTEGER | 总工作项数 |
| completed_items | INTEGER | 已完成数 |
| failed_items | INTEGER | 失败数 |

### work_items

| 字段 | 类型 | 说明 |
|------|------|------|
| item_id | TEXT | 主键 |
| task_id | TEXT | 关联任务 |
| language | TEXT | 生成语言 |
| persona | TEXT | 人设类型 |
| topic | TEXT | 话题 |
| skill | TEXT | 使用技能 |
| status | TEXT | pending/assigned/submitted/validated/failed |
| agent_id | TEXT | 分配的 Agent |

### submitted_records

存储 Agent 提交的生成结果，`fingerprint` 字段有 UNIQUE 约束实现去重。