# 独立数据生成 Skill 系统 实现计划

## 目标

在 V4 项目内创建一个**完全独立**的 `data_gen_skill/` 子系统，其他 Agent（如 SOLO）通过 MCP 工具接口调用，由调度器分布式分发给多个 Agent 并行生成 RWKV 训练数据。

## 核心特征

- ❌ **不调用外部 AI API**：Agent 自带 LLM 能力，自行生成数据
- ✅ **MCP 工具入口**：通过 MCP 协议暴露 `create_task`、`get_task` 等工具
- ✅ **调度器分发**：`Dispatcher` 将任务拆分为原子工作项，按需分发给 Agent
- ✅ **多 Agent 并行**：多个 Agent 同时拉取工作项，互不冲突
- ✅ **合规校验**：Agent 提交的结果经过 schema 验证后才入库
- ✅ **去重**：基于指纹避免重复生成
- ✅ **独立数据库**：`data/gen_data.db` 不与 V4 的 `tasks.db` 混用

## 系统流程

```
┌─────────────┐     MCP工具调用      ┌──────────────┐
│  SOLO Agent │ ──────────────────→ │  MCP Server  │
│  (调用者)    │ ←────────────────── │  (入口)       │
└─────────────┘     返回结果         └──────┬───────┘
                                           │ create_task()
                                           ▼
                                    ┌──────────────┐
                                    │  Dispatcher  │
                                    │  (调度器)     │
                                    └──────┬───────┘
                                           │ 拆分为 slots
                                           ▼
                              ┌─────────────────────────┐
                              │   work_items 队列 (DB)   │
                              │  slot_1, slot_2, ...     │
                              └─────┬──────────────┬─────┘
                                    │ pull_work()  │
                           ┌────────▼──┐      ┌────▼────────┐
                           │ Agent A   │      │ Agent B      │
                           │ (LLM生成) │      │ (LLM生成)    │
                           └────┬──────┘      └────┬─────────┘
                                │ submit_result() │
                                ▼                  ▼
                           ┌─────────────────────────┐
                           │   Schema Validator      │
                           │   (合规校验)             │
                           └───────────┬─────────────┘
                                       ▼
                           ┌─────────────────────────┐
                           │   gen_data.db           │
                           │   (结果存储 + 去重)     │
                           └─────────────────────────┘
```

## 目录结构

```
V4/
├── data_gen_skill/                # 独立的 data gen skill 系统
│   ├── __init__.py               # 包入口，导出公共接口
│   ├── mcp_server.py             # MCP 工具端点 (FastMCP)
│   ├── dispatcher.py             # 任务调度器
│   ├── db.py                     # SQLite 数据库管理
│   ├── models.py                 # 数据模型 (Task, WorkItem, Slot 等)
│   ├── schema_validator.py       # 生成结果合规校验器
│   ├── worker.py                 # Agent 参考实现 (拉取→生成→提交)
│   ├── config.py                 # 配置管理
│   ├── config.yaml               # 默认配置
│   └── data/
│       └── (运行时自动创建 gen_data.db)
```

## 实现步骤

### Step 1: 创建目录结构和数据模型

**文件**: `data_gen_skill/__init__.py`, `data_gen_skill/models.py`, `data_gen_skill/config.py`

- `models.py`：定义核心数据类
  - `GenTask`：顶层生成任务（generator_type, count, language_ratios, status, ...）
  - `WorkItem`：原子工作项（slot_id, language, persona, topic, skill, status, agent_id, ...）
  - `TaskStatus`：枚举（PENDING, RUNNING, COMPLETED, FAILED, CANCELLED）
  - `WorkItemStatus`：枚举（PENDING, ASSIGNED, SUBMITTED, VALIDATED, FAILED）
  - `SubmitResult`：Agent 提交的结果（work_item_id, agent_id, data, checksum, ...）
- `config.py`：配置管理，支持 YAML 文件和环境变量

### Step 2: 数据库层

**文件**: `data_gen_skill/db.py`

- 独立 SQLite 数据库 `data/gen_data.db`
- 表结构：
  - `gen_tasks`：顶层任务记录
  - `work_items`：原子工作项（含状态、分配 agent、结果引用）
  - `submitted_records`：Agent 提交的生成结果（原始 JSON）
  - `fingerprints`：去重指纹表
- 提供 DAO 方法：create_task, get_next_work_item, submit_result, update_status, ...

### Step 3: Schema 合规校验器

**文件**: `data_gen_skill/schema_validator.py`

- 复用 V4 生成器的 output schema 定义
- 验证 Agent 提交的数据是否符合：
  - 正确的 dialogue 结构（role, say/respond, thought, skill_calls）
  - TTS 格式 `{V:...,A:...}` 存在
  - thought 必须用英文
  - 多场景字段存在（如 clarify_then_success 等）
- 返回校验结果 (passed, errors list)

### Step 4: 任务调度器

**文件**: `data_gen_skill/dispatcher.py`

核心类 `GenTaskDispatcher`：

```python
class GenTaskDispatcher:
    def create_task(request: CreateTaskRequest) -> str:
        """创建生成任务，拆分为 slot→work_items，返回 task_id"""

    def next_work_items(agent_id: str, batch_size: int) -> list[WorkItem]:
        """Agent 拉取工作项（原子操作，防止重复分配）"""

    def submit_result(agent_id: str, work_item_id: str, data: dict) -> SubmitResult:
        """Agent 提交生成结果，触发校验和入库"""

    def get_task_status(task_id: str) -> TaskStatus:
        """查询任务进度"""

    def get_stats() -> dict:
        """系统统计"""
```

关键设计：
- `next_work_items()` 使用 `UPDATE ... WHERE status='pending' LIMIT N` 原子操作，天然支持多 Agent 并发
- 工作项超时机制：如果 Agent 分配后超时未提交，自动回收到 pending
- 去重：`submit_result()` 前检查指纹，避免重复入库

### Step 5: Agent 工作器参考实现

**文件**: `data_gen_skill/worker.py`

`GenAgentWorker` 类——展示 Agent 如何接入：

```python
class GenAgentWorker:
    def __init__(self, agent_id: str, dispatcher: GenTaskDispatcher):
        ...

    async def run_loop(self):
        """主循环：拉取工作 → 调用自身 LLM 生成 → 提交结果"""

    async def generate_for_item(self, item: WorkItem) -> dict:
        """Agent 使用自己的 LLM 生成一条数据（需要 Agent 自行实现）"""
```

- 包含一个完整的 mock 示例（用模板渲染代替实际 LLM 调用）
- 供真实 Agent 参考和替换

### Step 6: MCP Server

**文件**: `data_gen_skill/mcp_server.py`

基于 `fastmcp`（或 `mcp` SDK）创建 MCP Server，暴露以下工具：

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `create_gen_task` | generator_type, count, language_ratios, ... | 创建新生成任务 |
| `list_gen_tasks` | status_filter | 列出所有任务 |
| `get_gen_task` | task_id | 查看任务详情和进度 |
| `cancel_gen_task` | task_id | 取消任务 |
| `pull_work_items` | agent_id, batch_size | Agent 拉取工作项 |
| `submit_work_result` | agent_id, work_item_id, data | Agent 提交结果 |
| `export_rwkv` | task_id, output_path | 导出 RWKV 格式 |
| `get_system_stats` | — | 系统统计信息 |

### Step 7: 集成测试

- 创建测试脚本验证完整流程：创建任务 → Agent 拉取 → 生成 → 提交 → 校验 → 入库
- 并发测试：多个 Agent 同时拉取，验证不冲突
- 去重测试：相同指纹的提交被拒绝
- 测试完成后删除测试文件

## MCP 配置

Agent 需要在 `mcp.json` 或 `.trae/mcp.json` 中添加：

```json
{
  "mcpServers": {
    "data-gen-skill": {
      "command": "python",
      "args": ["-m", "data_gen_skill.mcp_server", "--config", "data_gen_skill/config.yaml"],
      "cwd": "${workspaceFolder}/V4"
    }
  }
}
```

## 注意事项

1. **不依赖外部 LLM API**：系统只做调度、校验、存储，Agent 自行负责 LLM 调用
2. **Worker 是参考实现**：真实的 Agent（如 SOLO）用自己的 LLM 替换 `generate_for_item()`
3. **原子操作**：`next_work_items()` 使用 SQLite 行锁，天然支持并发
4. **与 V4 的关系**：`data_gen_skill/` 复用 V4 的 `generators/`、`data/` 等资源，但拥有独立的数据库和调度逻辑