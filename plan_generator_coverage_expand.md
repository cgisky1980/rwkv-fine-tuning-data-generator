# 训练数据生成增强计划

## 目标
在现有生成器基础上，扩展覆盖更全面的训练数据场景。

---

## 一、现状分析

### 现有生成器 (V4)
| ID | 对应级别 | 主要场景 | 样本类型 |
|----|----------|----------|----------|
| no_tool | L0 | 纯对话 | 3-8轮闲聊 |
| single_skill | L1 | 单技能调用 | 5类：成功/错误/取消/无技能/建议puppet |
| complex_skill | L3 | 3-5技能调用 | 3类：多步骤/编排/并行 |
| mixed_dialog | L4 | 混合对话 | 3类：先闲聊后工具/先工具后闲聊/穿插 |

### 系统已支持的功能 ✅
- **语言分布**：前端/后端已完整支持 8 种语言比例配置 (zh/en/ja/ko/de/fr/es/ru)

### 当前缺失覆盖
1. **L2 级别**：2步技能链，参数缺失/模糊处理
2. **错误场景**：超时、部分成功
3. **对话模式**：澄清对话、恢复对话、确认对话

---

## 二、修改方案

### 方案 A：扩展现有生成器（推荐）
不创建新生成器，而是扩展现有 generator.yaml 配置和模板

#### 1. 扩展 single_skill (L1) - 增加更多错误类型
- 新增场景：
  - `timeout_case`: 技能调用超时
  - `partial_success_case`: 技能部分成功
  - `invalid_param_case`: 参数校验失败
- 修改文件：
  - `generators/single_skill/generator.yaml`
  - `generators/single_skill/templates/main.j2`

#### 2. 创建 L2 生成器
- 定位：2步技能链，参数缺失/模糊处理
- 场景：
  - `missing_param_case`: 用户缺少关键参数，助手询问澄清
  - `ambiguous_case`: 用户请求模糊，助手确认意图
  - `two_step_case`: 两步顺序调用，第二步依赖第一步结果
- 新增文件：
  - `generators/two_step_skill/generator.yaml`
  - `generators/two_step_skill/templates/main.j2`

#### 3. 扩展 mixed_dialog (L4) - 增加更多对话模式
- 新增场景：
  - `clarification_case`: 工具调用中的澄清对话
  - `recovery_case`: 错误后恢复尝试
  - `confirmation_case`: 关键操作前的确认对话
- 修改文件：
  - `generators/mixed_dialog/generator.yaml`
  - `generators/mixed_dialog/templates/main.j2`

#### 4. 增加多语言支持
- 修改 `generator.py` 的 `generate_batch` 方法
- 添加参数 `language_ratio`: 可配置语言分布
- 支持：zh(60%)/en(20%)/ja(10%)/其他(10%)

---

## 三、具体修改内容

### 3.1 single_skill 扩展
```yaml
# 新增场景配置
output_format:
  schema: |
    {
      "user_query": "...",
      "success_case": { ... },
      "error_case": { ... },        # 保持
      "cancelled_case": { ... },    # 保持
      "no_skill_case": { ... },     # 保持
      "puppet_case": { ... },       # 保持
      # 新增
      "timeout_case": {
        "thought": [...],
        "skill_calls": [{
          "step": 1,
          "skill_respond": "...",
          "skill_call": {...},
          "skill_output": { "status": "timeout", "reason": "Request timeout after 30s" },
          "skill_end": [...]
        }],
        "respond": "..."
      },
      "partial_success_case": {
        "skill_output": { "status": "partial", "result": {...}, "warnings": ["..."] },
        "respond": "..."
      }
    }
```

### 3.2 L2 生成器配置
```yaml
id: two_step_skill
name: 两步技能调用生成器
description: 生成两步技能调用的对话数据，L2级别
parameters:
  skills_per_record: 2
  level: L2
output_format:
  schema: |
    {
      "user_query": "...",
      "missing_param_case": { ... },    # 参数缺失，询问澄清
      "ambiguous_case": { ... },        # 意图模糊，确认后再执行
      "two_step_case": { ... },        # 两步顺序执行
      "error_propagation_case": { ... } # 第一步错误导致第二步失败
    }
```

### 3.3 语言分布配置
```python
# generator.py 新增参数
async def generate_batch(
    self,
    # ... 现有参数
    language: str = "zh",
    language_ratio: Optional[Dict[str, float]] = None,  # 新增
    topics: Optional[List[str]] = None,
):
```

---

## 四、执行计划

### 步骤 1: 扩展 single_skill (2技能点)
- [ ] 修改 `generators/single_skill/generator.yaml` - 新增 timeout_case, partial_success_case
- [ ] 修改 `generators/single_skill/templates/main.j2` - 支持新场景

### 步骤 2: 创建 L2 生成器 (3技能点)
- [ ] 创建 `generators/two_step_skill/` 目录
- [ ] 创建 `generator.yaml`
- [ ] 创建 `templates/main.j2`

### 步骤 3: 扩展 mixed_dialog (2技能点)
- [ ] 修改 `generators/mixed_dialog/generator.yaml` - 新增场景
- [ ] 修改模板支持新场景

### 步骤 4: 增加语言分布支持 (1技能点)
- [ ] 修改 `generator.py` - 添加 language_ratio 参数
- [ ] 修改 `_pick_persona` 方法支持多语言

### 步骤 5: 测试验证 (1技能点)
- [ ] 运行测试生成
- [ ] 检查输出质量

---

## 五、风险与注意事项

1. **模板复杂度**：新增场景会显著增加模板复杂度，需要仔细设计
2. **LLM 生成质量**：更多场景类型可能导致生成质量下降，需要调试
3. **配置一致性**：新增生成器需要与现有系统保持一致的配置结构

---

## 六、预期产出

修改完成后，训练数据将覆盖：

| 级别 | 场景类型 | 数量 |
|------|----------|------|
| L0 | 纯对话 | 现有 |
| L1 | 单技能 7 种场景 | 5 → 7 |
| L2 | 两步技能链 4 种场景 | 新增 |
| L3 | 复杂多技能 | 现有 |
| L4 | 混合对话 6 种场景 | 3 → 6 |
| 多语言 | zh/en/ja/... | 新增 |
