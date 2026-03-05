# V4 生成器开发指南

## 概述

V4 数据生成器采用**配置驱动**架构，通过 YAML 配置文件和 Jinja2 模板定义生成器行为。这种架构使得：

- **零代码扩展**：新增生成器只需添加配置文件，无需修改代码
- **AI 可读**：配置文件格式清晰，AI 可以读取并生成新配置
- **版本控制**：生成器配置可纳入 git 管理
- **高度复用**：模板可在多个生成器间共享

## 目录结构

```
V4/
├── generators/                          # 生成器配置目录
│   ├── _generators.yaml                # 生成器索引
│   ├── no_tool/                        # 无工具对话生成器
│   │   └── generator.yaml              # 生成器配置
│   ├── tool/                            # 工具调用生成器 (V3 L0-L4)
│   │   └── generator.yaml
│   ├── coding_assistant/               # 代码助手生成器（示例）
│   │   └── generator.yaml
│   └── movie_recommender/              # 电影推荐生成器（示例）
│       └── generator.yaml
├── templates/                           # Jinja2 模板目录
│   ├── _macros.j2                      # 共享宏定义
│   ├── no_tool/main.j2                 # 无工具对话模板
│   ├── tool/main.j2                     # 工具对话模板
│   └── coding_assistant/main.j2         # 代码助手模板
├── data/                                # 数据配置
│   ├── prompts_config.json             # 提示词配置（兼容）
│   ├── chat_topics.json                # 话题配置
│   └── persona_config.json              # Persona 配置
└── GENERATORS.md                       # 本文档
```

## V3 → V4 升级保留

本框架在 V3 基础上进行了以下**关键升级**，所有生成器必须保留：

### 1. Persona 简化结构

```json
{
  "name": "小明",
  "gender": "男",
  "age": "25",
  "race": "汉族",
  "tone": {
    "name": "温柔",
    "description": "说话轻声细语"
  },
  "optional_tics": ["~", "呀", "*微笑*"]
}
```

### 2. 用户画像 known_fields 机制

- 生成时**随机决定**哪些字段已知
- 对话中**必须体现**已知字段至少一个关键词

```json
{
  "name": "小明",
  "age": 25,
  "gender": "男",
  "location": "上海",
  "occupation": "程序员",
  "hobbies": ["摄影", "游戏"],
  "known_fields": ["name", "age", "occupation", "hobbies"]
}
```

### 3. TTS 格式（每句话必需）

```
(情绪+语速+语调, 动作) 说话内容
```

**示例**：
```
(开心地快速说, 挥手) 嗨！今天过得怎么样？
(温柔地慢慢说, 微笑) 我刚读完一本很有趣的书。
```

### 4. 涌现属性（不受控分布）

以下属性由 LLM 自然生成，不进行分布控制：

- **birthday**: 助手生日（系统级涌现属性）
- **time_context**: 时间/星期/天气（场景涌现属性）
- **emotion/action**: 不受控，随话题自然涌现

### 5. 8语言分布

```yaml
languages:
  zh: 70%   # 中文
  en: 15%   # 英语
  ja: 2%    # 日语
  ko: 2%    # 韩语
  de: 3%    # 德语
  fr: 3%    # 法语
  es: 3%    # 西班牙语
  ru: 2%    # 俄语
```

## 快速开始

### 1. 创建新生成器

```bash
# 复制模板目录
cp -r generators/template generators/my_generator
```

### 2. 修改配置

编辑 `generators/my_generator/generator.yaml`：

```yaml
id: my_generator
name: 我的生成器
description: 描述这个生成器的用途

# Persona 配置
persona:
  enabled: true
  fields: [name, gender, tone]

# 工具列表
tools:
  - name: search
    description: 搜索信息
    parameters:
      - name: query
        type: string
        required: true
    risk: low

# 输出格式
output_format:
  type: single_turn_with_tools
```

### 3. 编辑模板

修改 `templates/my_generator/main.j2`：

```jinja2
{# 我的生成器模板 #}
你是一个{{ persona.name }}。

用户问题是：{{ user_query }}

## 可用工具
{% for tool in tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}
```

### 4. 注册生成器

编辑 `generators/_generators.yaml`：

```yaml
generators:
  - id: my_generator
    name: 我的生成器
    description: 描述
    path: my_generator/generator.yaml
    enabled: true
```

## 配置规范

### generator.yaml 完整字段

```yaml
# 基础信息
id: generator_id           # 唯一标识符
name: 生成器名称           # 显示名称
description: 描述          # 详细描述

# 模板
template: templates/path/main.j2  # Jinja2 模板路径

# Persona 配置
persona:
  enabled: true/false      # 是否启用 Persona
  fields: [name, gender]   # 使用的 Persona 字段

# 用户画像配置
user_profile:
  enabled: true/false      # 是否启用用户画像
  ratio: 0.5               # 使用概率
  random_known_fields: true # 随机决定已知字段

# TTS 格式配置
tts:
  enabled: true
  per_sentence: true      # 每句话都需要前缀
  emotions: [开心, 难过]   # 情感列表
  actions: [挥手, 点头]    # 动作列表
  speeds: [快速, 正常]      # 语速列表
  tones: [说, 问]          # 语调列表

# 话题配置
topic:
  enabled: true
  source: data/chat_topics.json
  levels: [L0, L1, L2, L3, L4]

# 级别配置 (V3 L0-L4)
levels:
  L0:
    name: 基础对话
    tools_required: false
    rules: ["规则1", "规则2"]

# 工具定义
tools:
  - name: 工具名
    description: 描述
    parameters:
      - name: param1
        type: string
        required: true
    risk: low/high

# 输出格式
output_format:
  type: single_turn_with_tools
  fields:
    - name: field_name
      required_when: [assistant]

# 生成参数
parameters:
  min_turns: 1
  max_turns: 5
  require_tools: true/false

# 规则
rules:
  v4_common:
    - "规则1"
    - "规则2"
```

### 模板变量

| 变量 | 类型 | 说明 |
|------|------|------|
| `id` | string | 样本 ID |
| `level` | string | 级别 (L0-L4) |
| `language` | string | 语言代码 |
| `topic` | string | 话题名称 |
| `persona` | dict | Persona 信息 |
| `user_profile` | dict | 用户画像 |
| `user_profile_ref` | string | 格式化用户画像 |
| `time_context` | dict | 时间上下文 |
| `birthday` | string | 助手生日 |
| `tools` | list | 工具列表 |
| `rules` | list | 规则列表 |
| `level_config` | dict | 当前级别配置 |
| `parameters` | dict | 生成参数 |
| `tts` | dict | TTS 配置 |

## 示例生成器

### 无工具对话 (no_tool)

生成纯对话数据，无需工具调用。

```yaml
id: no_tool
name: 无工具对话生成器
description: 生成纯对话数据，无需工具调用

tools: []  # 无工具

parameters:
  min_turns: 3
  max_turns: 8
  require_tools: false
```

### 工具调用 (tool)

生成需要工具调用的对话数据，支持 L0-L4 五个级别。

```yaml
id: tool
name: 工具调用生成器
description: 生成需要工具调用的对话数据

levels:
  L0:
    name: 基础对话
    tools_required: false
  L1:
    name: 单工具调用
    tools_required: true
    tool_count: 1
  L2_clarification:
    name: 需求澄清
  L2_execution:
    name: 执行+澄清
  L3:
    name: 多工具链
    tool_count: ">=2"
```

### 代码助手 (coding_assistant)

生成代码审查、调试、解释等编程对话。

```yaml
id: coding_assistant
name: 代码助手生成器
description: 生成代码相关对话

tools:
  - name: read_file
    description: 读取代码文件
  - name: search_code
    description: 搜索代码库

persona:
  specialties:
    languages: [Python, JavaScript]
    expertise_areas: [代码审查, Bug调试]
```

## AI 生成新生成器

当需要创建新生成器时，可以使用以下提示词让 AI 帮助生成配置：

```
请为一个 [领域] 生成器创建配置：

1. 生成器基本信息：
   - 名称：[名称]
   - 描述：[功能描述]

2. Persona 配置：
   - 需要的 Persona 字段
   - 是否有特殊属性

3. 工具列表：
   - 工具名称和描述
   - 参数定义
   - 风险等级

4. 输出格式：
   - JSON 结构定义
   - 必需字段

5. 特殊规则：
   - 领域特定的生成规则
```

## 最佳实践

1. **保持配置简洁**：避免过度复杂的配置
2. **使用共享宏**：将通用内容提取到 `_macros.j2`
3. **版本控制配置**：将生成器配置纳入 git 管理
4. **文档注释**：为每个生成器添加清晰描述
5. **测试验证**：创建生成器后进行数据质量验证

## API 接口

### 获取可用生成器

```bash
GET /api/config/generators
```

响应：
```json
{
  "generators": [
    {
      "id": "no_tool",
      "name": "无工具对话生成器",
      "description": "生成纯对话数据",
      "enabled": true,
      "default": true
    }
  ]
}
```

## 常见问题

### Q: 如何添加自定义规则？

在 `generator.yaml` 的 `rules.v4_common` 中添加：

```yaml
rules:
  v4_common:
    - "我的自定义规则1"
    - "我的自定义规则2"
```

### Q: 如何支持多轮对话？

在模板中使用循环生成多轮对话，参数控制轮数：

```jinja2
{% for i in range(parameters.min_turns, parameters.max_turns) %}
轮次 {{ i }}: ...
{% endfor %}
```

### Q: 如何调试模板？

使用以下命令测试模板渲染：

```python
from V4.pipeline.generator import UniversalGenerator
gen = UniversalGenerator("no_tool", api_key="...")
# 渲染模板测试
template = gen.template.render(...)
```

## 相关文档

- [README.md](../README.md) - 主文档
- [CHAT_TOPICS.md](data/chat_topics.md) - 话题配置
- [PERSONA.md](data/persona_config.md) - Persona 配置
