"""
V4 通用生成器引擎

配置驱动的数据生成器，支持通过 YAML 配置文件和 Jinja2 模板定义生成行为。
保留所有 V3→V4 升级点。
"""

import asyncio
import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from jinja2 import Environment, FileSystemLoader, Template

from .common import (
    LLMClient,
    PersonaManager,
    normalize_language,
    get_root_dir,
    load_json_config,
    extract_json_from_text,
    generate_assistant_birthday,
)
from .generators import GeneratorLoader, get_generator_loader


class UniversalGenerator:
    """V4 通用生成器引擎 - 配置驱动"""

    def __init__(
        self,
        generator_id: str,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        supports_json_object: bool = True,
        provider_id: str = None,
    ):
        self.id = generator_id
        self.config = get_generator_loader().get_generator(generator_id)
        if not self.config:
            raise ValueError(f"Generator not found: {generator_id}")

        self.llm = LLMClient(api_key=api_key, base_url=base_url, model=model, supports_json_object=supports_json_object, provider_id=provider_id)
        self.root_dir = get_root_dir()

        # V4 Persona 管理
        self.persona_manager = PersonaManager(
            self.root_dir / "data" / "persona_config.json"
        )

        # V4 工具配置
        self.tools_config = load_json_config("tools_config.json")

        # 模板引擎
        self._init_template_engine()

    def _init_template_engine(self):
        """初始化 Jinja2 模板引擎"""
        template_path = get_generator_loader().get_template_path(self.id)
        if not template_path:
            raise ValueError(f"Template not found for generator: {self.id}")
        
        template_dir = template_path.parent
        loader = FileSystemLoader(str(template_dir))
        self.jinja_env = Environment(
            loader=loader,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        self.template = self.jinja_env.get_template(template_path.name)

    async def generate_batch(
        self,
        total: int,
        temperature: float,
        seed: Optional[int],
        user_profile_ratio: float,
        concurrency: int,
        max_tokens: Optional[int] = None,
        language: str = "zh",
        topics: Optional[List[str]] = None,
    ) -> List[Tuple[Dict, Optional[str], Optional[str]]]:
        """批量生成数据"""
        semaphore = asyncio.Semaphore(concurrency)
        seed_val = seed or 0

        async def run_one(idx):
            async with semaphore:
                try:
                    return await self.generate_one(
                        idx,
                        temperature,
                        seed_val,
                        user_profile_ratio,
                        max_tokens,
                        language,
                        topics,
                    )
                except Exception as e:
                    return {}, "error", str(e)

        tasks = [run_one(i) for i in range(total)]
        return await asyncio.gather(*tasks)

    async def generate_one(
        self,
        idx: int,
        temperature: float,
        seed: int,
        user_profile_ratio: float,
        max_tokens: Optional[int],
        language: str = "zh",
        topics: Optional[List[str]] = None,
    ) -> Tuple[Dict, Optional[str], Optional[str]]:
        """生成单条数据 - 包含所有 V4 升级"""
        rng = random.Random((seed or 0) + idx)

        try:
            # 1. V4 Persona 简化结构
            persona = self._pick_persona(seed, idx, language)

            # 2. V4 用户画像（random known_fields）
            profile, user_profile_ref = self._pick_user_profile(
                seed, idx, user_profile_ratio
            )

            # 3. V4 话题
            topic_config = get_generator_loader().get_topic_config(self.id)
            topic_levels = topic_config.get("levels", [])
            topic_info = self._pick_topic(topics, seed, topic_levels)

            # 4. V4 涌现属性（不受控分布）
            birthday = generate_assistant_birthday(seed)
            time_context = self._generate_time_context(seed)

            # 5. 构建模板变量
            try:
                context = self._build_context(
                    idx=idx,
                    seed=seed,
                    persona=persona,
                    user_profile=profile,
                    user_profile_ref=user_profile_ref,
                    topic=topic_info,
                    time_context=time_context,
                    birthday=birthday,
                    language=language,
                )
            except Exception as e:
                raise Exception(f"Error in _build_context: {e}, topic_info={topic_info}, persona={persona}") from e

            # 7. 渲染模板
            prompt = self.template.render(**context)

            # 8. 调用 LLM
            response = await self.llm.generate(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens or 4000,
                json_mode=True,
            )
            data = json.loads(extract_json_from_text(response))

            # 9. 后处理
            result = self._post_process(
                data=data,
                idx=idx,
                seed=seed,
                persona=persona,
                user_profile_ref=user_profile_ref,
                topic_info=topic_info,
                time_context=time_context,
                birthday=birthday,
                language=language,
                tools_list=context["_tools_list"],
            )

            return result, None, None

        except Exception as e:
            return {}, "error", str(e)

    def _pick_persona(self, seed: int, idx: int, language: str) -> Dict[str, Any]:
        """选择 Persona - 使用 PersonaManager"""
        rng = random.Random((seed or 0) + idx * 2654435761)

        persona = self.persona_manager.generate_random_persona(language)
        if not persona:
            return {"name": "助手", "gender": "女", "tone": {"name": "温柔"}, "language": language}
        
        # 只保留对应语言的口癖
        if "optional_tics" in persona and isinstance(persona["optional_tics"], dict):
            lang_tics = persona["optional_tics"].get(language, [])
            persona["optional_tics"] = lang_tics

        return persona

    def _pick_user_profile(
        self, seed: int, idx: int, ratio: float
    ) -> Tuple[Dict, Optional[str]]:
        """选择用户画像 - V4 known_fields 机制"""
        if ratio <= 0:
            return {"known_fields": []}, None

        rng = random.Random((seed or 0) + idx * 114)
        if rng.random() > ratio:
            return {"known_fields": []}, None

        profile = self.persona_manager.generate_random_user_profile(
            seed=(seed or 0) + idx * 114
        )
        ref = self.persona_manager.format_user_profile(profile)
        return profile, ref

    def _pick_topic(self, topics: Optional[List[str]], seed: int, levels: Optional[List[str]] = None) -> Dict[str, Any]:
        """选择话题"""
        topics_config = load_json_config("chat_topics.json")
        topic_list = topics_config.get("topics", [])

        if not topic_list:
            return {"category": "General", "topic": "General", "dialogue_pattern": "Free"}

        rng = random.Random((seed or 0) + 12345)

        # 过滤指定话题 (按 category 过滤)
        if topics:
            available = [t for t in topic_list if t.get("category") in topics]
            if available:
                chosen_topic = rng.choice(available)
            else:
                chosen_topic = rng.choice(topic_list)
        else:
            chosen_topic = rng.choice(topic_list)

        category = chosen_topic.get("category", "General")
        topic_levels = chosen_topic.get("levels", {})

        if not topic_levels:
            return {"category": category, "topic": category, "dialogue_pattern": "Free"}

        # 根据生成器配置的 levels 过滤
        if levels:
            available_levels = [l for l in topic_levels.keys() if l in levels]
        else:
            available_levels = list(topic_levels.keys())
        
        if not available_levels:
            return {"category": category, "topic": category, "dialogue_pattern": "Free"}
        
        chosen_level = rng.choice(available_levels)
        level_data = topic_levels[chosen_level]

        return {
            "category": category,
            "topic": level_data.get("topic", category),
            "dialogue_pattern": level_data.get("dialogue_pattern", "Free"),
            "level": chosen_level,
        }

    def _generate_time_context(self, seed: int) -> Dict[str, str]:
        """生成时间上下文 - V4 涌现属性"""
        rng = random.Random((seed or 0) + 888)

        days_ago = rng.randint(0, 30)
        hours = rng.randint(8, 22)

        random_date = datetime.now() - timedelta(days=days_ago)
        random_date = random_date.replace(hour=hours, minute=rng.randint(0, 59))

        time_str = random_date.strftime("%Y/%m/%d %H:%M")

        weekdays = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        ]
        weekday = weekdays[random_date.weekday()]

        month = random_date.month
        if month in [12, 1, 2]:
            weathers = ["晴天", "多云", "阴天", "小雪", "寒冷"]
        elif month in [3, 4, 5]:
            weathers = ["晴天", "多云", "阴天", "小雨", "春风和煦"]
        elif month in [6, 7, 8]:
            weathers = ["晴天", "多云", "阴天", "雷阵雨", "炎热"]
        else:
            weathers = ["晴天", "多云", "阴天", "小雨", "凉爽"]

        weather = rng.choice(weathers)

        return {
            "datetime": time_str,
        }

    def _build_context(
        self,
        idx: int,
        seed: int,
        persona: Dict[str, Any],
        user_profile: Dict[str, Any],
        user_profile_ref: Optional[str],
        topic: Dict[str, Any],
        time_context: Dict[str, str],
        birthday: str,
        language: str,
    ) -> Dict[str, Any]:
        """构建模板渲染上下文"""
        rng = random.Random((seed or 0) + idx)
        
        # 获取配置
        params = get_generator_loader().get_parameters(self.id)
        tts_config = get_generator_loader().get_tts_config(self.id)
        tools = get_generator_loader().get_tools(self.id)
        
        # 安全获取 rules
        rules = []
        if isinstance(self.config, dict):
            rules = self.config.get("rules", [])
        elif isinstance(self.config, list):
            rules = self.config

        # 准备工具列表
        tools_list = [
            {
                "name": t.name,
                "description": t.description,
                "alias": t.alias,
                "parameters": t.parameters,
                "risk": t.risk,
                "help": t.help,
            }
            for t in tools
        ]

        # 用户语言：90% 与助手语言相同，10% 使用不同语言
        if rng.random() < 0.9:
            user_language = language
        else:
            other_languages = [l for l in ["zh", "en", "ja", "ko", "de", "fr", "es", "ru"] if l != language]
            user_language = rng.choice(other_languages)

        return {
            "id": f"{self.id}_{seed}_{idx}",
            "language": language,
            "user_language": user_language,
            "topic": topic.get("topic", ""),
            "persona": persona,
            "user_profile": user_profile,
            "user_profile_ref": user_profile_ref,
            "time_context": time_context,
            "birthday": birthday,
            "skills": tools_list,
            "rules": rules,
            "parameters": params,
            "tts": tts_config or {},
            "_tools_list": tools_list,
        }

    def _post_process(
        self,
        data: Dict,
        idx: int,
        seed: int,
        persona: Dict[str, Any],
        user_profile_ref: Optional[str],
        topic_info: Dict[str, Any],
        time_context: Dict[str, str],
        birthday: str,
        language: str,
        tools_list: List[Dict],
    ) -> Dict:
        """后处理生成结果"""
        rng = random.Random((seed or 0) + idx + 999)
        
        def extract_used_skills(item: Any) -> List[str]:
            """从生成的数据中提取实际使用的技能名称"""
            used = set()
            if isinstance(item, dict):
                if "skill_calls" in item:
                    for call in item["skill_calls"]:
                        if isinstance(call, dict) and "skill_doc" in call:
                            skill_name = call["skill_doc"].get("name")
                            if skill_name:
                                used.add(skill_name)
                if "dialogue" in item:
                    for turn in item["dialogue"]:
                        used.update(extract_used_skills(turn))
            elif isinstance(item, list):
                for subitem in item:
                    used.update(extract_used_skills(subitem))
            return list(used)
        
        def add_skills_usage_to_item(item: Any, skills_usage: List[Dict]):
            """将 skills_usage 添加到数据项中"""
            if isinstance(item, dict):
                if "user_query" in item:
                    item["skills_usage"] = skills_usage
                if "dialogue" in item:
                    for turn in item["dialogue"]:
                        add_skills_usage_to_item(turn, skills_usage)
                if "type" in item and item.get("type") == "tool":
                    item["skills_usage"] = skills_usage
            elif isinstance(item, list):
                for subitem in item:
                    add_skills_usage_to_item(subitem, skills_usage)
        
        used_skill_names = extract_used_skills(data)
        
        used_skills = []
        for skill in tools_list:
            if skill["name"] in used_skill_names:
                used_skills.append({
                    "name": skill["name"],
                    "alias": skill["alias"],
                    "description": skill["description"],
                })
        
        available_skills = [
            skill for skill in tools_list
            if skill["name"] not in used_skill_names
        ]
        
        rng.shuffle(available_skills)
        total_needed = rng.randint(4, 5)
        need_more = max(0, total_needed - len(used_skills))
        random_skills = available_skills[:need_more]
        
        random_skills_simplified = [
            {
                "name": s["name"],
                "alias": s["alias"],
                "description": s["description"],
            }
            for s in random_skills
        ]
        
        final_skills_usage = used_skills + random_skills_simplified
        rng.shuffle(final_skills_usage)
        
        add_skills_usage_to_item(data, final_skills_usage)
        
        return {
            "id": f"{self.id}_{seed}_{idx}",
            "generator_type": self.id,
            "language": language,
            "topic": topic_info.get("topic", ""),
            "system": {
                "persona": persona,
                "user_profile": user_profile_ref,
                "time_context": time_context,
                "birthday": birthday,
            },
            "turns": data if isinstance(data, list) else [data],
        }

    def _build_combined_tics(self, persona: dict, lang: str) -> List[str]:
        """构建 combined tics - V4 语言风格"""
        tics = []

        lang_tics = {
            "zh": ["~", "啦", "呢", "呀", "哈", "哦"],
            "en": ["um", "uh", "like", "you know", "right"],
            "ja": ["~", "ね", "よ", "わ", "な"],
            "ko": ["~", "요", "지", "잖아"],
            "de": ["äh", "also", "quasi", "halt"],
            "fr": ["euh", "quoi", "ben", "alors"],
            "es": ["eh", "pues", "bueno", "vale"],
            "ru": ["э", "ну", "короче", "типа"],
        }

        if lang in lang_tics:
            tics.extend(lang_tics[lang][:2])

        return list(set(tics))

    async def close(self):
        """关闭生成器"""
        await self.llm.close()


# 便捷函数
def create_generator(generator_id: str, api_key: str) -> UniversalGenerator:
    """创建生成器实例"""
    return UniversalGenerator(generator_id, api_key)
