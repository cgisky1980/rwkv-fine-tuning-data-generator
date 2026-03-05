import asyncio
import json
import random
from abc import ABC, abstractmethod
from typing import Any

from .common import (
    LLMClient,
    PersonaManager,
    normalize_language,
    get_root_dir,
    load_json_config,
)


class BaseSkillGenerator(ABC):
    """V4 有技能生成器基类 - 基于 V3 BaseGenerator 改造"""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ):
        self.llm = LLMClient(api_key=api_key, base_url=base_url, model=model)
        self.root_dir = get_root_dir()
        self.persona_manager = PersonaManager(
            self.root_dir / "data" / "persona_config.json"
        )
        self.prompts_config = load_json_config("prompts_config.json")
        self.topics_config = load_json_config("chat_topics.json")
        self.skills_config = load_json_config("skills_config.json")

    def _pick_refs_count(self, seed: int, idx: int) -> int:
        cfg = (self.prompts_config.get("system_prompts") or {}).get("refs_generation") or {}
        try:
            probability = float(cfg.get("probability", 0.0))
        except Exception:
            probability = 0.0
        probability = max(0.0, min(1.0, probability))

        try:
            min_items = int(cfg.get("min_items", 0))
        except Exception:
            min_items = 0
        try:
            max_items = int(cfg.get("max_items", 0))
        except Exception:
            max_items = 0

        min_items = max(0, min(3, min_items))
        max_items = max(0, min(3, max_items))
        if max_items < min_items:
            max_items = min_items

        rng = random.Random(int(seed) + int(idx) * 2654435761 + 911)
        if probability <= 0 or rng.random() >= probability:
            return 0
        if max_items <= 0:
            return 0
        return rng.randint(min_items, max_items)

    async def _generate_refs(self, user_say: str, count: int, seed: int) -> list[str]:
        if count <= 0:
            return []

        if getattr(self.llm, "api_key", None) == "sk-test":
            base = str(user_say or "").strip()
            if not base:
                base = "用户提出了一个请求。"
            out = [
                f"背景信息：用户的请求与\"{base[:30]}\"相关。",
                "提示：如果涉及时间词（今天/明天），需要结合 user.time 解释。",
                "偏好：用户更喜欢简洁、可执行的回答。"
            ][:count]
            return out

        prompt = f"""你在为对话样本生成 user.refs（模拟 RAG 检索结果）。

## 要求
- 只输出严格合法的 JSON 数组（不要 Markdown、不要解释）。
- 数组长度必须严格等于 {count}。
- 每个元素必须是字符串。
- 内容必须与 user.say 强相关，像"检索到的背景信息片段"，不要编造超出 user.say 的个性画像细节。
- 如果 user.say 不包含地点/人名/账户等信息，就不要凭空补充这些专属细节。

## user.say
{json.dumps(user_say, ensure_ascii=False)}
"""
        text = await self.llm.generate(prompt, temperature=0.4, max_tokens=400, json_mode=True)
        try:
            v = json.loads(text)
        except Exception:
            return []
        if not isinstance(v, list):
            return []
        refs: list[str] = []
        for x in v:
            s = str(x).strip()
            if not s:
                continue
            refs.append(s)
            if len(refs) >= count:
                break
        if len(refs) != count:
            return []
        return refs

    async def _generate_user_query(self, skills: list[dict], topic_info: dict) -> str:
        """Generate a complex user query based on selected skills and topic."""
        skill_names = [t.get("name") for t in skills]
        skill_desc_str = json.dumps(
            [
                {k: v for k, v in t.items() if k in ["name", "description"]}
                for t in skills
            ],
            ensure_ascii=False,
            indent=2,
        )

        prompt = f"""
You are a User Simulator.
Your task is to generate a realistic User Query that requires the Assistant to use the available skills to solve it.

## Context
- Topic: {topic_info.get("topic", "General")} ({topic_info.get("category", "General")})
- Available Skills:
{skill_desc_str}

## Requirements
1. The query MUST be in **CHINESE**.
2. The query MUST require using the provided skills.
3. Make it natural and conversational.

## Output Format
Just return the User Query string. Do not output anything else.
"""
        try:
            query = await self.llm.generate(prompt, temperature=0.8, max_tokens=100)
            return query.strip().strip('"').strip("'")
        except Exception:
            return f"请帮我处理关于 {topic_info.get('topic')} 的事情，可能需要用到 {', '.join(skill_names)}。"

    def _get_skill_category(self, skill_name: str, skill_description: str) -> str:
        # Try to find category from topics_config.skill_categories mapping first
        skill_categories = self.topics_config.get("skill_categories", {})
        for cat, skills in skill_categories.items():
            if skill_name in skills:
                return cat

        # Fallback to keyword matching
        name_lower = skill_name.lower()
        desc_lower = skill_description.lower() if skill_description else ""

        if any(kw in name_lower or kw in desc_lower for kw in ["weather", "天气"]):
            return "theme_media"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["time", "时间", "calendar", "日历", "schedule", "日程"]
        ):
            return "system"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["calculator", "计算器", "math", "数学"]
        ):
            return "system"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["email", "邮件", "message", "消息", "send", "发送"]
        ):
            return "communication"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["search", "搜索", "web", "网络"]
        ):
            return "application"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["map", "地图", "location", "位置", "地址"]
        ):
            return "application"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["music", "音乐", "play", "播放"]
        ):
            return "theme_media"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["translation", "翻译", "translate"]
        ):
            return "application"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["stock", "股票", "finance", "金融", "price"]
        ):
            return "application"
        if any(kw in name_lower or kw in desc_lower for kw in ["news", "新闻"]):
            return "application"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["alarm", "闹钟", "reminder", "提醒"]
        ):
            return "todo"

        if any(kw in name_lower or kw in desc_lower for kw in ["file", "文件"]):
            return "filesystem"
        if any(
            kw in name_lower or kw in desc_lower
            for kw in ["folder", "directory", "目录"]
        ):
            return "folder"
        if any(kw in name_lower or kw in desc_lower for kw in ["app", "应用"]):
            return "application"

        return "other"

    async def close(self):
        await self.llm.close()

    def _pick_persona(self, seed: int | None, idx: int, language: str = "zh") -> dict:
        state = random.getstate()
        random.seed((seed or 0) + idx * 2654435761)
        try:
            raw = self.persona_manager.generate_random_persona(
                language=normalize_language(language)
            )

            # Fetch allowed emotions and actions from config
            emotions = self.persona_manager.data.get("emotions", [])
            all_actions = self.persona_manager.data.get("actions", [])
            if isinstance(all_actions, list) and "nill" not in all_actions:
                all_actions = ["nill", *all_actions]

            # Randomly select half of the actions to reduce hallucination/noise
            actions = all_actions
            if all_actions:
                sample_size = max(1, len(all_actions) // 2)
                actions = random.sample(all_actions, sample_size)
                if "nill" not in actions:
                    actions = ["nill", *actions]
        finally:
            random.setstate(state)

        personality = (
            raw.get("personality") if isinstance(raw.get("personality"), dict) else {}
        )
        gender = raw.get("gender") if isinstance(raw.get("gender"), dict) else {}
        identity = raw.get("identity") if isinstance(raw.get("identity"), dict) else {}
        tone = raw.get("tone") if isinstance(raw.get("tone"), dict) else {}
        user_title = (
            raw.get("user_title") if isinstance(raw.get("user_title"), dict) else {}
        )

        tone_desc = (
            personality.get("tone_desc", "")
            if isinstance(personality.get("tone_desc"), str)
            else ""
        )

        def _extract_tics(src: dict, lang_code: str) -> list[str]:
            t = src.get("optional_tics")
            if isinstance(t, list):
                return [str(x).strip() for x in t if str(x).strip()]
            if isinstance(t, dict):
                lang_key = "zh" if normalize_language(lang_code) == "zh" else "en"
                v = t.get(lang_key, [])
                if isinstance(v, list):
                    return [str(x).strip() for x in v if str(x).strip()]
            return []

        lang_code = normalize_language(raw.get("language"))
        identity_tics = _extract_tics(identity, lang_code)
        personality_tics = _extract_tics(personality, lang_code)
        combined_tics = list(dict.fromkeys([*identity_tics, *personality_tics]))

        # Ensure tone field is populated
        tone_name = tone.get("name", "")
        tone_description = tone.get("description", "")
        if not tone_description and tone_desc:
            tone_description = tone_desc
            if not tone_name:
                tone_name = f"{personality.get('name', '')}语气"

        return {
            "name": raw.get("name")
            if isinstance(raw.get("name"), str) and raw.get("name")
            else "小助",
            "gender": {
                "name": gender.get("name", ""),
                "description": gender.get("description", ""),
            },
            "identity": {
                "name": identity.get("name", ""),
                "description": identity.get("description", ""),
            },
            "personality": {
                "name": personality.get("name", ""),
                "description": personality.get("description", ""),
            },
            "tone": {
                "name": tone_name,
                "description": tone_description,
            },
            "optional_tics": combined_tics,
            "user_title": {
                "name": user_title.get("name", ""),
                "description": user_title.get("description", ""),
            },
            "language": normalize_language(raw.get("language")),
            "role": "assistant",
            "allowed_emotions": emotions,
            "allowed_actions": actions,
        }

    def _resolve_verbal_tic_pool(self, persona: dict, seed: int) -> list[str]:
        def _as_list(v: Any) -> list:
            return v if isinstance(v, list) else []

        def _dedupe_keep_order(items: list[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for x in items:
                s = str(x).strip()
                if not s:
                    continue
                if s in seen:
                    continue
                seen.add(s)
                out.append(s)
            return out

        def _extract_tics(src: dict, lang_key: str) -> list[str]:
            t = src.get("optional_tics")
            if isinstance(t, list):
                return [str(x).strip() for x in t if str(x).strip()]
            if isinstance(t, dict):
                v = t.get(lang_key, [])
                if isinstance(v, list):
                    return [str(x).strip() for x in v if str(x).strip()]
            return []

        lang_key = "zh" if normalize_language(str(persona.get("language", "zh"))) == "zh" else "en"

        root = _as_list(persona.get("optional_tics"))
        if root:
            pool = [str(x).strip() for x in root if str(x).strip()]
            pool = _dedupe_keep_order(pool)
            if pool:
                return pool

        identity_name = ""
        personality_name = ""
        identity = persona.get("identity") if isinstance(persona.get("identity"), dict) else {}
        personality = (
            persona.get("personality") if isinstance(persona.get("personality"), dict) else {}
        )
        if isinstance(identity, dict):
            identity_name = str(identity.get("name", "")).strip()
        if isinstance(personality, dict):
            personality_name = str(personality.get("name", "")).strip()

        identity_entry = None
        personality_entry = None
        try:
            for x in self.persona_manager.data.get("identities", []) or []:
                if isinstance(x, dict) and str(x.get("name", "")).strip() == identity_name:
                    identity_entry = x
                    break
            for x in self.persona_manager.data.get("personalities", []) or []:
                if isinstance(x, dict) and str(x.get("name", "")).strip() == personality_name:
                    personality_entry = x
                    break
        except Exception:
            identity_entry = None
            personality_entry = None

        pool = []
        if isinstance(identity_entry, dict):
            pool.extend(_extract_tics(identity_entry, lang_key))
        if isinstance(personality_entry, dict):
            pool.extend(_extract_tics(personality_entry, lang_key))

        pool = _dedupe_keep_order(pool)
        if pool:
            return pool

        rng = random.Random(seed)
        return [rng.choice(["嗯", "呃", "那个", "总之"])] if lang_key == "zh" else [rng.choice(["well", "uh", "hmm", "anyway"])]

    def _pick_user_profile(self, seed: int | None, idx: int, ratio: float):
        ratio = float(ratio)
        if ratio <= 0:
            return None, None
        if ratio >= 1:
            ratio = 1.0

        state = random.getstate()
        random.seed((seed or 0) + idx * 11400714819323198485)
        try:
            use_profile = random.random() < ratio
            if not use_profile:
                return None, None
            profile = self.persona_manager.generate_random_user_profile()
            ref = self.persona_manager.format_user_profile(profile)
            if not isinstance(ref, str) or not ref.strip():
                return None, None
            return profile, ref
        finally:
            random.setstate(state)

    def _pick_topic(self, topics_config: dict, target_level: str, seed: int | None):
        topics_list = topics_config.get("topics", [])
        if not topics_list:
            return {
                "category": "general",
                "topic": "日常对话",
                "dialogue_pattern": "问答",
            }

        state = random.getstate()
        random.seed((seed or 0) + 12345)
        try:
            topic_entry = random.choice(topics_list)
        finally:
            random.setstate(state)

        category = topic_entry.get("category", "general")
        levels = topic_entry.get("levels", {})
        
        if target_level in levels:
            level_info = levels[target_level]
        else:
            level_info = list(levels.values())[0] if levels else {}

        return {
            "category": category,
            "topic": level_info.get("topic", "日常对话"),
            "dialogue_pattern": level_info.get("dialogue_pattern", "问答"),
        }

    def _skill_subset(
        self,
        extra_skills: int,
        seed: int,
        topic_category: str,
        scenario_probs: dict | None = None,
    ) -> tuple[list[dict], str]:
        if extra_skills <= 0:
            return [], "none"

        all_skills = self.skills_config.get("skills", [])
        if not all_skills:
            return [], "none"

        available = [t for t in all_skills if isinstance(t, dict) and t.get("name")]
        if not available:
            return [], "none"

        default_probs = {"matching": 0.7, "mismatched": 0.2, "none": 0.1}
        probs = scenario_probs or default_probs

        state = random.getstate()
        random.seed(seed)
        try:
            scenario = random.choices(
                population=["matching", "mismatched", "none"],
                weights=[
                    probs.get("matching", 0.7),
                    probs.get("mismatched", 0.2),
                    probs.get("none", 0.1),
                ],
                k=1,
            )[0]
        finally:
            random.setstate(state)

        if scenario == "none":
            return [], "none"

        if scenario == "matching":
            target_cat = topic_category
        else:
            other_cats = [t for t in available if t.get("category") != topic_category]
            if not other_cats:
                target_cat = topic_category
            else:
                state = random.getstate()
                random.seed(seed + 111)
                try:
                    other = random.choice(other_cats)
                    target_cat = other.get("category", "other")
                finally:
                    random.setstate(state)

        candidates = [t for t in available if t.get("category") == target_cat]
        if not candidates:
            candidates = available

        num_skills = min(extra_skills, len(candidates))
        state = random.getstate()
        random.seed(seed + 222)
        try:
            selected = (
                random.sample(candidates, k=num_skills)
                if num_skills <= len(candidates)
                else random.sample(candidates, k=len(candidates))
            )
        finally:
            random.setstate(state)

        return selected, scenario

    @abstractmethod
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
    ) -> tuple[dict, str | None, str | None]:
        pass

    async def generate_batch(
        self,
        total: int,
        skills_per_record: int,
        temperature: float,
        seed: int | None,
        user_profile_ratio: float,
        concurrency: int,
        max_tokens: int | None = None,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        frequency_penalty: float | None = None,
        skills_min_count: int = 0,
        skills_max_count: int = 0,
        scenario_probs: dict | None = None,
        language_distribution: dict[str, float] | None = None,
    ) -> list[tuple[dict, str | None, str | None]]:
        semaphore = asyncio.Semaphore(concurrency)

        async def guarded_generate(idx: int) -> tuple[dict, str | None, str | None]:
            async with semaphore:
                # Determine language
                lang = "zh"
                if language_distribution:
                    try:
                        langs = list(language_distribution.keys())
                        weights = list(language_distribution.values())
                        # Use a seed-based random for reproducibility
                        rng = random.Random((seed or 0) + idx * 999)
                        lang = rng.choices(langs, weights=weights, k=1)[0]
                    except Exception:
                        pass

                persona = self._pick_persona(seed=seed, idx=idx, language=lang)
                profile, user_profile_ref = self._pick_user_profile(
                    seed=seed, idx=idx, ratio=user_profile_ratio
                )

                topics_config = self.topics_config
                topic_info = self._pick_topic(
                    topics_config, self.level_name, seed=(seed or 0) + idx
                )

                skills, skill_scenario = self._get_skills(
                    idx=idx,
                    skills_per_record=skills_per_record,
                    topic_category=topic_info.get("category"),
                    scenario_probs=scenario_probs,
                )

                if skills:
                    actual_count = len(skills)
                    if actual_count < skills_min_count:
                        needed = skills_min_count - actual_count
                        additional, _ = self._skill_subset(
                            extra_skills=needed,
                            seed=(seed or 0) + idx + 10000,
                            topic_category=topic_info.get("category"),
                            scenario_probs=scenario_probs,
                        )
                        skills.extend([t for t in additional if t not in skills])
                    elif skills_max_count > 0 and actual_count > skills_max_count:
                        skills = skills[:skills_max_count]

                return await self.generate_one(
                    idx=idx,
                    skills=skills,
                    persona=persona,
                    user_profile_ref=user_profile_ref,
                    temperature=temperature,
                    seed=(seed or 0) + idx,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    presence_penalty=presence_penalty,
                    frequency_penalty=frequency_penalty,
                )

        tasks = [guarded_generate(i) for i in range(total)]
        results = await asyncio.gather(*tasks)
        return results

    @abstractmethod
    def _get_skills(
        self,
        idx: int,
        skills_per_record: int,
        topic_category: str,
        scenario_probs: dict | None,
    ) -> tuple[list[dict], str]:
        pass

    @property
    @abstractmethod
    def level_name(self) -> str:
        pass
