# V4 有工具对话生成器创建计划

## 背景概述

基于 V4 的无工具对话生成器（no_tool），参照 V3 的 L1-L4 分级，创建有工具的对话生成器。

### 已完成的生成器

| 类别 | 描述 | 对应 V3 级别 | 状态 |
|------|------|--------------|------|
| **single_tool** | 单工具调用 | L1 | ✅ 已完成 |
| **complex_tool** | 复杂任务调用 | L2 + L3 | ✅ 已完成 |
| **mixed_dialog** | 多轮混合对话 | L4 | ✅ 已完成 |
| **no_tool** | 无工具对话 | L0 | ✅ 已存在 |

---

## 目录结构

```
V4/generators/
├── no_tool/           # 无工具对话生成器
│   ├── generator.yaml
│   └── templates/
│       ├── _macros.j2
│       ├── export.j2
│       └── main.j2
├── single_tool/        # 单工具调用生成器
│   ├── generator.yaml
│   └── templates/
│       ├── _macros.j2
│       ├── export.j2
│       └── main.j2
├── complex_tool/       # 复杂任务调用生成器
│   ├── generator.yaml
│   └── templates/
│       ├── _macros.j2
│       ├── export.j2
│       └── main.j2
└── mixed_dialog/      # 多轮混合对话生成器
    ├── generator.yaml
    └── templates/
        ├── _macros.j2
        ├── export.j2
        └── main.j2
```

---

## 各类生成器设计

### 1. single_tool（单工具调用）
- **场景**：单工具执行，参数明确，返回规范
- **参数**：max_tools_per_record: 1
- **场景概率**：matching: 0.7, mismatched: 0.2, none: 0.1
- **输出**：success_case 和 error_case 两个样本

### 2. complex_tool（复杂任务调用）
- **场景**：多步骤工具链（≥2步），鲁棒性处理
- **参数**：max_tools_per_record: 3
- **场景类型**：multi_step, missing_param, ambiguous, no_match, tool_error
- **输出**：完整的多步骤轨迹

### 3. mixed_dialog（多轮混合对话）
- **场景**：闲聊和工具使用混合
- **参数**：chat_turns: 2, tool_turns: 1
- **场景概率**：matching: 1.0（100%成功）
- **输出**：闲聊轮 + 工具轮

---

## 工具定义

工具定义使用 V3 的 `data/tools_config.json`，包含：
- theme_set_season
- theme_set_weather
- background_audio_control
- theme_set_effects
- assistant_voice_control
- weather_api
- theme_list_presets
- delete_file
- write_file
- read_file
- list_directory
- search_files
- send_message
- execute_command
- open_folder
- open_application
- create_todo
- update_todo
- delete_todo
- list_todos
- search_todos
- execute_python_script

---

## 下一步

1. 在 pipeline 中注册新生成器
2. 测试生成器输出
3. 调整模板和参数优化生成质量
