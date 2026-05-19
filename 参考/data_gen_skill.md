# 数据生成 Skill (DataGenSkill) 参考文档

## 概述

`DataGenSkill` 是 V4 数据生成系统的统一接口服务，提供：
- 需求澄清+技能调用场景的数据生成
- 基于指纹的去重机制，避免生成重复数据
- RWKV 训练数据导出
- 可被其他 Agent 调用的清晰接口

## 文件结构

```
generators/clarify_skill/
├── generator.yaml              # 生成器配置
└── templates/
    ├── _macros.j2              # 共享宏（TTS、Persona、用户画像、时间上下文）
    ├── main.j2                 # 主提示词模板
    ├── export.j2               # MD格式导出模板
    └── rwkv.j2                 # RWKV训练格式导出模板

pipeline/data_gen_skill.py      # DataGenSkill 服务类
pipeline/export_template.py     # 已更新：支持 clarify_skill 类型识别和导出
```

## 核心接口

### DataGenSkill 类

```python
from pipeline.data_gen_skill import DataGenSkill, GenRequest

skill = DataGenSkill()

# 生成数据
request = GenRequest(
    generator_type="clarify_skill",
    count=10,
    language="zh",
    temperature=0.7,
    skip_duplicate=True,  # 自动跳过重复
)
result = skill.generate(request)
# result.task_id, result.is_duplicate, result.records_generated

# 同步等待生成完成
result = skill.generate_sync(request, timeout=300)

# 导出 RWKV 格式
export_result = skill.export_rwkv(task_ids=["task_xxx"], output_path="output.jsonl")

# 查询已生成记录
records = skill.list_generated({"generator_type": "clarify_skill"})

# 获取统计
stats = skill.get_stats()

# 检查重复
dup = skill.check_duplicate(request)
```

### GenRequest 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| generator_type | str | "clarify_skill" | 生成器类型 |
| count | int | 10 | 生成数量 |
| temperature | float | 0.7 | 温度 |
| seed | int? | None | 随机种子 |
| concurrency | int | 4 | 并发数 |
| language | str | "zh" | 语言 |
| topic | str? | None | 话题 |
| user_profile_ratio | float | 0.3 | 用户画像比例 |
| provider_id | str? | None | LLM Provider |
| max_tokens | int | 8192 | 最大token |
| skip_duplicate | bool | True | 是否跳过重复 |

## 去重机制

- 基于 `generator_type + language + topic + count + temperature` 生成 SHA256 指纹（前16位）
- 指纹存储在 `data/tasks.db` 的 `gen_fingerprints` 表
- `skip_duplicate=True` 时自动跳过已完成的相同配置任务

## clarify_skill 生成器

### 场景说明

三种场景同时生成：
1. **clarify_then_success**: 用户请求模糊 → 助手澄清 → 用户补充 → 技能调用成功
2. **clarify_then_error**: 用户请求模糊 → 助手澄清 → 用户补充 → 技能调用失败
3. **no_clarify_needed**: 用户请求清晰 → 助手直接调用技能（对照样本）

### 输出格式

多轮对话格式，包含 `dialogue` 数组，每轮有 `role`、`say`/`respond`、`thought`、`skill_calls` 等字段。

### 关键规则

- 澄清轮 thought 的 action 必须是 "clarify"
- 澄清提问一次只问1-2个关键问题
- thought 使用英文，respond 使用 persona 语言
- 每句话必须以 `{V:说话风格描述,A:动作}` 开头

## 数据库表

### gen_fingerprints

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| fingerprint | TEXT | 去重指纹（UNIQUE） |
| task_id | TEXT | 关联任务ID |
| generator_type | TEXT | 生成器类型 |
| language | TEXT | 语言 |
| topic | TEXT | 话题 |
| skills_hash | TEXT | 技能组合hash |
| record_count | INTEGER | 记录数 |
| created_at | TEXT | 创建时间 |
