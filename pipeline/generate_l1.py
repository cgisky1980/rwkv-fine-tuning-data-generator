import json
import random

from .generate_base import BaseSkillGenerator


class L1Generator(BaseSkillGenerator):
    level_name = "L1"

    def _get_skills(
        self,
        idx: int,
        skills_per_record: int,
        topic_category: str,
        scenario_probs: dict | None,
    ) -> tuple[list[dict], str]:
        if scenario_probs is None:
            scenario_probs = {"matching": 0.7, "mismatched": 0.2, "none": 0.1}

        rng = random.Random(idx * 1315423911)

        skills_config = self.skills_config
        skills_list = skills_config.get("skills", [])

        if not skills_list:
            return [], "none"

        pool = []
        for skill in skills_list:
            skill_dict = {
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "parameters": skill.get("parameters", {}),
                "risk": skill.get("risk", "low"),
                "confirmation_required": skill.get("confirmation_required", False),
                "category": self._get_skill_category(
                    skill.get("name", ""), skill.get("description", "")
                ),
            }
            if skill.get("alias"):
                skill_dict["alias"] = skill.get("alias")
            pool.append(skill_dict)

        num_skills_to_select = max(0, int(skills_per_record))

        if num_skills_to_select == 0:
            return [], "none"

        topic_suitable_cats = []
        if topic_category:
            topics = self.topics_config.get("topics", [])
            for t in topics:
                if t.get("category") == topic_category:
                    topic_suitable_cats = t.get("suitable_skill_categories", [])
                    break

        selected = []
        scenario = "none"

        if topic_suitable_cats:
            matching_skills = [
                t for t in pool if t.get("category") in topic_suitable_cats
            ]
            non_matching_skills = [
                t for t in pool if t.get("category") not in topic_suitable_cats
            ]

            for skill in matching_skills:
                skill["_is_matching"] = True
            for skill in non_matching_skills:
                skill["_is_matching"] = False

            prob_matching = scenario_probs.get("matching", 0.7)
            prob_mismatched = scenario_probs.get("mismatched", 0.2)
            prob_none = scenario_probs.get("none", 0.1)
            total_prob = prob_matching + prob_mismatched + prob_none
            prob_matching /= total_prob
            prob_mismatched /= total_prob
            prob_none /= total_prob

            rand_val = rng.random()

            if rand_val < prob_matching:
                scenario = "matching"
                source_pool = matching_skills
            elif rand_val < prob_matching + prob_mismatched:
                scenario = "mismatched"
                source_pool = non_matching_skills
            else:
                scenario = "none"
                return [], "none"

            if not source_pool:
                scenario = "none"
                return [], "none"

            categories = list(set(t.get("category") for t in source_pool))
            rng.shuffle(categories)

            cat_idx = 0
            while len(selected) < num_skills_to_select and cat_idx < len(categories):
                cat = categories[cat_idx % len(categories)]
                skills_in_cat = [t for t in source_pool if t.get("category") == cat]
                if skills_in_cat:
                    selected.append(skills_in_cat[0])
                cat_idx += 1

            if len(selected) < num_skills_to_select:
                remaining = [t for t in source_pool if t not in selected]
                rng.shuffle(remaining)
                for skill in remaining:
                    if len(selected) >= num_skills_to_select:
                        break
                    if skill not in selected:
                        selected.append(skill)

        return selected, scenario

    async def generate_one(
        self,
        idx: int,
        skills: list[dict],
        persona: dict,
        user_profile_ref: str | None,
        temperature: float,
        seed: int,
        max_tokens: int | None = None,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        result_type: str = "success",
    ) -> tuple[dict | list[dict], str | None, str | None]:
        if not skills:
            import random

            all_skills = self.skills_config.get("skills", [])
            if all_skills:
                skills_count = random.randint(2, min(5, len(all_skills)))
                skills = random.sample(all_skills, skills_count)
                result_type = "error_no_match"

        try:
            tic_pool = self._resolve_verbal_tic_pool(persona, seed)
            persona["optional_tics"] = tic_pool

            topic_info = self._pick_topic(self.topics_config, "L1", seed=seed)

            user_query_content = await self._generate_user_query(skills, topic_info)

            refs_count = self._pick_refs_count(seed=seed, idx=idx)
            refs = await self._generate_refs(user_say=user_query_content, count=refs_count, seed=seed)

            prompt = self._build_one_shot_prompt(
                skills=skills,
                persona=persona,
                user_query=user_query_content,
                refs=refs,
                user_profile_ref=user_profile_ref,
                topic_info=topic_info,
                seed=seed,
                result_type=result_type,
            )
            
            gen_kwargs = {"temperature": temperature, "json_mode": True}
            if max_tokens is not None:
                gen_kwargs["max_tokens"] = max_tokens
            if top_p is not None:
                gen_kwargs["top_p"] = top_p
            if presence_penalty is not None:
                gen_kwargs["presence_penalty"] = presence_penalty
            if frequency_penalty is not None:
                gen_kwargs["frequency_penalty"] = frequency_penalty

            self.llm.model = "deepseek-chat"
            text = await self.llm.generate(prompt, **gen_kwargs)

            if not text:
                return (
                    {"raw_response": None},
                    "empty_response",
                    "LLM returned empty response",
                )

            from .common import extract_json_from_text

            cleaned_text = extract_json_from_text(text)
            try:
                raw_payload = json.loads(cleaned_text)
            except Exception:
                return (
                    {"raw_response": text, "cleaned_text": cleaned_text},
                    "invalid_json",
                    "LLM response not valid JSON",
                )

            payloads = []

            def process_trajectory(assistant_data, suffix=""):
                if "thought" not in assistant_data:
                    assistant_data["thought"] = []
                if "skill_calls" not in assistant_data:
                    assistant_data["skill_calls"] = []
                if "respond" not in assistant_data:
                    assistant_data["respond"] = ""
                
                for i, sc in enumerate(assistant_data["skill_calls"]):
                    if "step" not in sc:
                        sc["step"] = i + 1

                from datetime import datetime

                p = {
                    "id": f"L1_{seed}_{idx:06d}{suffix}",
                    "system": {
                        "persona": persona,
                        "user_profile_ref": user_profile_ref
                    },
                    "user": {
                        "say": user_query_content,
                        "skills_usage": skills,
                        "refs": refs
                    },
                    "assistant": assistant_data,
                    "meta": {
                        "level": "L1",
                        "step_count": len(assistant_data["skill_calls"]),
                    },
                    "time": (
                        f"[{datetime.now().year}/{datetime.now().month}/{datetime.now().day} "
                        f"{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}]"
                    )
                }
                p["user"]["time"] = p["time"]

                if suffix == "_err":
                    p["meta"]["is_simulated_error"] = True
                    p["meta"]["result_type"] = "error"
                elif suffix == "_cancelled":
                    p["meta"]["is_simulated_error"] = True
                    p["meta"]["result_type"] = "cancelled"
                else:
                    p["meta"]["result_type"] = result_type
                
                return p

            from datetime import datetime

            if result_type == "success":
                if "success_case" in raw_payload and "error_case" in raw_payload and "cancelled_case" in raw_payload:
                    success_p = process_trajectory(raw_payload["success_case"], "")
                    error_p = process_trajectory(raw_payload["error_case"], "_err")
                    cancelled_p = process_trajectory(raw_payload["cancelled_case"], "_cancelled")
                    payloads = [success_p, error_p, cancelled_p]
                elif "success_case" in raw_payload and "error_case" in raw_payload:
                    success_p = process_trajectory(raw_payload["success_case"], "")
                    error_p = process_trajectory(raw_payload["error_case"], "_err")
                    payloads = [success_p, error_p]
                else:
                    if "thought" in raw_payload:
                        payloads = [process_trajectory(raw_payload, "")]
                    else:
                        return ({"raw_response": text}, "structure_error", "Missing success_case/error_case/cancelled_case")
            else:
                if "thought" in raw_payload:
                    payloads = [process_trajectory(raw_payload, "")]
                else:
                    key = next(iter(raw_payload))
                    if isinstance(raw_payload[key], dict) and "thought" in raw_payload[key]:
                        payloads = [process_trajectory(raw_payload[key], "")]
                    else:
                        return ({"raw_response": text}, "structure_error", "Invalid single case structure")

            return payloads, None, None

        except Exception as e:
            import traceback

            traceback.print_exc()
            return {"raw_response": None}, "exception", str(e)

    def _build_one_shot_prompt(
        self,
        skills: list[dict],
        persona: dict,
        user_query: str,
        refs: list[str],
        user_profile_ref: str | None,
        topic_info: dict,
        seed: int,
        result_type: str = "success",
    ) -> str:
        base_context = self._build_prompt(
            skills=skills,
            persona=persona,
            user_profile_ref=user_profile_ref,
            seed=seed,
            topic_info=topic_info,
        )

        refs_json = json.dumps(refs, ensure_ascii=False, indent=2)

        if result_type == "success":
            task_instruction = """## 任务：多样本生成 (Multi-Trajectory Generation)
你是专家级的数据生成器。你的任务是根据给定的 User Query，生成**三个独立**的交互轨迹：
1. **success_case**: 技能调用**成功**返回正常数据，并给出完美回答。
2. **error_case**: 模拟技能调用**失败**（如网络超时、500错误），Assistant 需妥善处理错误并安抚用户。
3. **cancelled_case**: 模拟用户**取消**操作，Assistant 需确认取消并回复用户。

注意：三个场景必须针对**同一个** User Query。
"""
            output_schema = """### 输出 JSON 结构
必须输出包含三个对象的 JSON：
```json
{
  "success_case": {
    "thought": [ { "observation": "...", "reasoning": "...", "reflection": "...", "action": "..." ],
    "skill_calls": [
      {
        "step": 1,
        "skill_respond": "Checking...",
        "skill_doc": "技能的详细使用说明和例子",
        "skill_call": { "name": "...", "arguments": { ... } },
        "skill_output": { "status": "success", "result": { ... } },
        "skill_end": [ ...4-step post-skill CoT... ]
      }
    ],
    "respond": "Final answer..."
  },
  "error_case": {
    "thought": [ ... ],
    "skill_calls": [
      {
        "step": 1,
        "skill_respond": "...",
        "skill_doc": "技能的详细使用说明和例子",
        "skill_call": { "name": "...", "arguments": { ... } },
        "skill_output": { "status": "error", "error": { ... } },
        "skill_end": [ ...4-step post-skill CoT... ]
      }
    ],
    "respond": "..."
  },
  "cancelled_case": {
    "thought": [ ... ],
    "skill_calls": [
      {
        "step": 1,
        "skill_respond": "...",
        "skill_doc": "技能的详细使用说明和例子",
        "skill_call": { "name": "...", "arguments": { ... } },
        "skill_output": { "status": "cancelled", "reason": "User cancelled the operation" },
        "skill_end": [ ...4-step post-skill CoT... ]
      }
    ],
    "respond": "..."
  }
}
```
"""
        elif result_type == "error_no_match":
            task_instruction = """## 任务：无匹配技能场景生成
用户提出了一个请求，但现有的技能**无法**解决该问题。
Assistant 必须识别出技能不匹配，不调用任何技能，并直接回复用户。
"""
            output_schema = """### 输出 JSON 结构
```json
{
  "thought": [ ...Reflexion steps realizing no skill fits... ],
  "skill_calls": [],
  "respond": "Explain inability to help due to missing skills..."
}
```
"""
        else:
            task_instruction = f"## 任务：生成交互轨迹 ({result_type})"
            output_schema = """### 输出 JSON 结构
```json
{
  "thought": [ ... ],
  "skill_calls": [ ... ],
  "respond": "..."
}
```
"""

        core_rules = """### 核心规则
#### 1. 技能模拟 (Skill Simulation)
- **skill_respond 说明**: 这是**调用技能之前**的说明，体现助手理解了用户的意图，向用户说明将要做什么。
  - 助手把 skill 视为**自己的技能或魔法**，根据自己的种族和身份做特征化表达
  - 如果技能有**别名（alias）**，必须优先使用别名称呼技能
  - 例如：如果是猫娘，技能有别名「目录探查」，可以说「喵~让我用「目录探查」魔法帮您看看~」
  - 例如：如果是精灵，技能有别名「圣典阅览」，可以说「以星光之名，让我为您施展「圣典阅览」」
  - 例如：如果是普通助理，技能有别名「天象探查术」，可以说「好的，让我用「天象探查术」帮您查看天气」
- **skill_doc 说明**: 这是被调用技能的详细使用说明和例子，包含：
  - 技能的完整功能描述
  - 参数的详细说明
  - 使用示例
  - 注意事项和最佳实践
  *注意：skill_doc 只在决定调用某个技能后才添加，用于提供详细的使用指导。*
- **Mock Data**: 你必须为每个技能调用生成逼真的 `skill_output` (JSON格式)。
  - `success_case`: 返回正常数据。
  - `error_case`: 返回错误结构 (e.g. `{"status": "error", ...}`).
  - `cancelled_case`: 返回取消结构 (e.g. `{"status": "cancelled", ...}`).

#### 2. 思考范式 (Chain of Thought)
- **格式**: JSON 对象数组。
- **内容**: 每个思考块必须包含 4 步:
  1. `observation`: 观测到的事实（用户输入或技能结果）。
  2. `reasoning`: 分析事实，决定下一步。
  3. `reflection`: 反思风险、幻觉检查。
  4. `action`: 具体行动（调用技能或回复）。
- **语言**: Thought 必须完全使用 **ENGLISH**。
- **Step Skill End**: `skill_calls[i].skill_end 必须是"技能执行后的复盘"，Observation 必须引用该步的 `skill_output`，Action 描述"下一步要做什么"（下一次技能调用或结束并回复）。

#### 3. 助手回复 (Respond)
- **风格**: 严格遵循 Persona 的语气、口癖。
- **标签**: 每句话前必须加 `{V:说话风格描述,A:动作}` (例如 `{V:开心地微笑,A:挥手} 好的！`)。
- **语言**: 使用 Persona 定义的语言。
"""

        prompt = f"""{base_context}

{task_instruction}

### 输入信息
**User Query**: "{user_query}"
**Reference Knowledge**:
{refs_json}

{core_rules}

{output_schema}
"""
        return prompt

    def _build_prompt(
        self,
        skills: list[dict],
        persona: dict,
        user_profile_ref: str | None,
        seed: int,
        topic_info: dict | None = None,
    ) -> str:
        prompts = self.prompts_config
        system_prompts = prompts.get("system_prompts", {})

        persona_json = json.dumps(persona, ensure_ascii=False, indent=2)
        upr = json.dumps(user_profile_ref, ensure_ascii=False)
        skill_list_json = json.dumps(skills, ensure_ascii=False, indent=2)

        base_template = system_prompts.get("base", "").format(
            persona_json=persona_json, user_profile_ref=upr
        )

        user_title = (
            persona.get("user_title", {})
            if isinstance(persona.get("user_title"), dict)
            else {}
        )
        user_title_name = (
            user_title.get("name") if isinstance(user_title.get("name"), str) else ""
        )

        emotions_str = ", ".join(persona.get("allowed_emotions", []))
        actions_str = ", ".join(persona.get("allowed_actions", []))

        common_rules = system_prompts.get("common_rules", "").format(
            user_title_name=json.dumps(user_title_name, ensure_ascii=False),
            allowed_emotions_list=emotions_str,
            allowed_actions_list=actions_str,
        )
        thought_language_rules = system_prompts.get("thought_language_rules_strict", "").strip()
        respond_tag_rules = system_prompts.get("respond_tag_rules_strict", "").format(
            allowed_emotions_list=emotions_str,
            allowed_actions_list=actions_str,
        ).strip()

        tone = persona.get("tone", {})
        tone_name = tone.get("name", "Unknown")
        tone_desc = tone.get("description", "")
        tic_pool = persona.get("optional_tics", [])

        rng = random.Random(seed + 888)
        p_lang_code = persona.get("language", "zh")

        def code_to_name(c):
            m = {
                "zh": "Chinese",
                "en": "English",
                "ja": "Japanese",
                "ko": "Korean",
                "de": "German",
                "fr": "French",
            }
            return m.get(c, "Chinese")

        assistant_lang_name = code_to_name(p_lang_code)
        user_lang_name = assistant_lang_name

        if p_lang_code != "zh":
            if rng.random() < 0.5:
                user_lang_name = "Chinese"
        else:
            if rng.random() < 0.05:
                user_lang_name = "English"

        style_and_tone_instruction = f"""## Style & Tone
- **Identity**: {persona.get("identity", {}).get("name", "Unknown")} - {persona.get("identity", {}).get("description", "")}
- **Personality**: {persona.get("personality", {}).get("name", "Unknown")} - {persona.get("personality", {}).get("description", "")}
- **Tone**: {tone_name} - {tone_desc}
- **Verbal Tics**: OPTIONAL and occasional. If used, place at the START or END naturally.
  - Do NOT wrap tics in parentheses or brackets.
  - Do NOT force every response to include a tic.
- **Verbal Tic Pool**: {json.dumps(tic_pool, ensure_ascii=False)}
{thought_language_rules}
{respond_tag_rules}
"""

        language_instruction = f"""## Language Rules (STRICT)
- **User** MUST speak in **{user_lang_name}**.
- **Assistant** MUST speak in **{assistant_lang_name}**.
- **Cross-Language Enforcement**: If User and Assistant languages differ, the Assistant MUST NOT switch language to match the User. The Assistant MUST stick to **{assistant_lang_name}**.
"""

        from datetime import datetime

        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_context_instruction = f"""## 当前时间上下文 (Time Context)
用户当前的实际时间是: {current_time_str}
**重要**: 如果用户的请求中包含相对时间词汇（如"今天"、"明天"、"本周"），你必须基于上述当前时间计算出具体的日期参数。"""

        skill_list_header = system_prompts.get("skill_list_header", "")

        if topic_info is None:
             topic_info = {"category": "General", "topic": "General", "dialogue_pattern": "General"}

        topic_instruction = f"""话题设置:
- 话题分类: {topic_info.get("category")}
- 话题主题: {topic_info.get("topic")}
- 对话模式: {topic_info.get("dialogue_pattern")}

注意: L1 级别侧重于单轮对话，重点考察技能调用的准确性和异常处理。"""

        parts = [
            base_template,
            style_and_tone_instruction,
            language_instruction,
            common_rules,
            topic_instruction,
            skill_list_header,
            skill_list_json,
            time_context_instruction,
        ]
        return "\n\n".join(part for part in parts if part).strip()
