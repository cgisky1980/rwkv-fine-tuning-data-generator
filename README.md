# V4 Data Generator - Complete System

基于 V3 打造的下一代对话数据生成器，具备完整的任务管理、后台异步处理、实时进度追踪和 RWKV 训练数据导出功能。

## ✨ 核心特性

### 1. 完整的任务管理系统
- **独立任务存储**: 每个任务生成独立的数据文件
- **SQLite 索引**: 任务元数据和统计信息持久化存储
- **任务生命周期**: 支持创建/运行/完成/失败/取消全状态流转
- **导出追踪**: 自动记录已导出任务，避免重复导出

### 2. 后台异步处理
- **线程池并发**: 可配置并发工作线程数（默认4个）
- **实时进度**: WebSocket 推送 + API 轮询双模式
- **任务取消**: 支持取消正在运行的任务
- **自动重试**: 失败任务可重新提交

### 3. 详细的配置选项

#### 语言比例分配（参考 V3）
- 中文 (ZH): 70%
- 英文 (EN): 15%
- 日文 (JA): 2%
- 韩文 (KO): 2%
- 德文 (DE): 3%
- 法文 (FR): 3%
- 西班牙文 (ES): 3%
- 俄文 (RU): 2%

#### 级别比例分配（工具对话）
- L0 - 无工具: 10%
- L1 - 单工具: 15%
- L2 - 双工具: 25%
- L3 - 三工具: 25%
- L4 - 四工具+: 25%

### 4. 数据可视化
- **实时进度**: 进度条 + 速度 + 预估剩余时间
- **系统概览**: 任务统计、生成记录数
- **分布分析**: 话题、情绪、动作、工具使用统计

### 5. RWKV 训练导出
- **自动去重**: 基于任务导出历史，避免数据重复
- **多任务合并**: 支持选择多个任务合并导出
- **格式支持**: multi_turn / single_turn / instruction
- **内置工具**: 已整合 json2binidx_tool，一键导出 binidx

## 📁 项目结构

```
V4/
├── pipeline/
│   ├── task_manager.py         # 任务管理（SQLite）
│   ├── task_processor.py       # 后台处理器（线程池）
│   ├── data_analyzer.py        # 数据分析器
│   ├── rwkv_converter.py       # RWKV 格式转换
│   ├── binidx_converter.py     # binidx 转换
│   ├── common.py               # 公共工具
│   ├── generate_base.py        # 生成器基类
│   ├── generate_no_tool.py     # 无工具生成器
│   ├── generate_tool.py        # 工具生成器
│   └── json2binidx_tool/       # 已整合的 RWKV 工具
├── web/
│   ├── backend/
│   │   └── main.py             # FastAPI 后端 + WebSocket
│   └── frontend/
│       └── index.html          # 任务管理界面
├── data/
│   ├── tasks/                  # 任务数据文件
│   │   ├── task_20240207_143022_abc123.jsonl
│   │   └── ...
│   ├── export/                 # 导出文件
│   └── tasks.db                # SQLite 数据库
├── tests/
│   └── verify_system.py        # 系统验证
└── requirements.txt
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd V4
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python web/backend/main.py
```

### 3. 访问界面

- Web 界面: http://localhost:8080 (前端)
- API 文档: http://localhost:8000/docs (Swagger)

## 📊 使用流程

### 创建任务
1. 进入"创建任务"标签页
2. 设置任务名称、生成数量、温度等参数
3. 调整语言比例和级别比例（必须都等于100%）
4. 点击"创建任务"

### 监控进度
1. 切换到"任务队列"标签页
2. 实时查看所有任务状态
3. 支持取消正在运行的任务

### 数据导出
1. 切换到"数据导出"标签页
2. 选择已完成的任务（自动去重）
3. 选择导出格式（multi_turn/single_turn/instruction）
4. 点击"导出 RWKV 格式"或"导出 binidx"

## 🔌 API 端点

### 任务管理
```
POST   /api/tasks              # 创建任务
GET    /api/tasks              # 列出所有任务
GET    /api/tasks/{id}         # 获取任务详情
POST   /api/tasks/{id}/cancel  # 取消任务
DELETE /api/tasks/{id}         # 删除任务
GET    /api/tasks/{id}/data    # 获取任务数据
GET    /api/tasks/{id}/download # 下载数据文件
```

### 实时进度
```
GET    /api/progress           # 获取所有活跃任务进度
GET    /api/progress/{id}      # 获取特定任务进度
WS     /ws                     # WebSocket 实时推送
```

### 数据统计
```
GET    /api/stats/overview     # 系统概览统计
GET    /api/stats/tasks/{id}   # 任务详细统计
GET    /api/stats/aggregate    # 聚合统计（多任务）
```

### 数据导出
```
POST   /api/export/rwkv        # 导出 RWKV 格式
POST   /api/export/binidx      # 导出 binidx 格式
GET    /api/export/download/{filename}  # 下载导出文件
```

### 配置选项
```
GET    /api/config/languages   # 语言配置
GET    /api/config/levels      # 级别配置
```

## 💡 高级功能

### 批量导出（去重）

```python
import requests

# 导出多个任务（自动去重）
response = requests.post('http://localhost:8000/api/export/rwkv', json={
    "task_ids": ["task_001", "task_002", "task_003"],
    "format_type": "multi_turn",
    "shuffle": True,
    "output_name": "training_batch_1"
})

print(response.json())
```

### 自定义任务配置

```python
from pipeline.task_manager import TaskConfig, get_task_manager
from pipeline.task_processor import get_task_processor

# 创建自定义配置
config = TaskConfig(
    generator_type="tool",
    count=1000,
    temperature=0.8,
    concurrency=8,
    # 语言比例
    lang_ratio_zh=50,
    lang_ratio_en=30,
    lang_ratio_ja=10,
    lang_ratio_ko=10,
    lang_ratio_de=0,
    lang_ratio_fr=0,
    lang_ratio_es=0,
    lang_ratio_ru=0,
    # 级别比例
    ratio_l0=0,
    ratio_l1=20,
    ratio_l2=30,
    ratio_l3=30,
    ratio_l4=20
)

# 提交任务
task_manager = get_task_manager()
processor = get_task_processor(max_workers=8)

task = task_manager.create_task("Custom Task", config)
processor.submit_task(task.name, config)
```

## 🎨 界面预览

### 创建任务
- 基本配置：名称、类型、数量、温度、并发数
- 语言比例：8种语言独立调节
- 级别比例：L0-L5 工具复杂度分配

### 任务队列
- 实时状态显示（pending/running/completed/failed/cancelled）
- 进度条 + 生成速度 + 剩余时间
- 取消运行中任务

### 数据统计
- 系统概览：总任务数、总记录数、运行中、已完成
- 分布图表：话题、情绪、动作、工具使用统计

### 数据导出
- 选择多个任务（自动去重）
- 格式选择：multi_turn / single_turn / instruction
- 一键导出 binidx

## 🔧 系统架构

```
┌─────────────────────────────────────────┐
│           前端 (浏览器)                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ 创建任务 │ │ 任务队列 │ │ 数据导出 │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼ WebSocket/HTTP
┌─────────────────────────────────────────┐
│           FastAPI 后端                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ 任务API │ │ 进度推送 │ │ 统计API │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│           任务调度器 (线程池)             │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ 任务队列 │ │ 线程池  │ │ 状态管理 │   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│           数据层                         │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ SQLite  │ │  任务文件│ │  导出文件│   │
│  │ (索引)  │ │ (.jsonl)│ │ (.jsonl)│   │
│  └─────────┘ └─────────┘ └─────────┘   │
└─────────────────────────────────────────┘
```

## 📝 数据存储

### 任务文件格式
每个任务生成独立的 JSONL 文件：

```
data/tasks/task_20240207_143022_a1b2c3.jsonl
```

内容格式：
```json
{"id": "...", "level": "V4_NoTool", "turns": [...]}
{"id": "...", "level": "V4_Tool", "user": {...}, "assistant": {...}}
```

### SQLite 数据库
存储任务元数据和统计信息：

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT,
    config TEXT,      -- JSON
    stats TEXT,       -- JSON
    data_file TEXT,   -- 关联的数据文件路径
    export_status TEXT
);
```

## 🎯 开发计划

- [x] 任务管理系统
- [x] 后台异步处理
- [x] 实时进度追踪
- [x] 详细配置选项
- [x] 数据分布统计
- [x] RWKV 导出（去重）
- [ ] 高级可视化图表
- [ ] 任务模板系统
- [ ] 批量任务调度
- [ ] 数据质量检测

## 📄 License

Apache 2.0
