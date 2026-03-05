import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx

_llm_providers_config_path = None


def get_providers_config_path() -> Path:
    global _llm_providers_config_path
    if _llm_providers_config_path is None:
        _llm_providers_config_path = Path(__file__).parent.parent / "data" / "llm_providers.json"
    return _llm_providers_config_path


def update_provider_supports_json_object(provider_id: str, supports: bool) -> bool:
    """Auto-update provider config to disable/enable json_object support"""
    config_path = get_providers_config_path()
    if not config_path.exists():
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        providers = data.get("providers", {})
        if provider_id in providers:
            old_value = providers[provider_id].get("supports_json_object", True)
            providers[provider_id]["supports_json_object"] = supports
            data["providers"] = providers

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[LLMClient] Auto-updated provider {provider_id}: supports_json_object {old_value} -> {supports}")
            return True
    except Exception as e:
        print(f"[LLMClient] Failed to update provider config: {e}")

    return False


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        supports_json_object: bool = True,
        provider_id: Optional[str] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.supports_json_object = supports_json_object
        self.provider_id = provider_id

    async def generate(self, prompt: str, **kwargs) -> str:
        response_format = None
        if kwargs.pop("json_mode", None) and self.supports_json_object:
            response_format = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        messages = [{"role": "user", "content": prompt}]
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }
        if response_format:
            body["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    resp = await client.post(url, json=body, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    message = data["choices"][0]["message"]
                    content = message.get("content", "") or message.get("reasoning", "")

                    if not content:
                        print(f"[LLMClient] Warning: Both content and reasoning are empty")
                        print(f"[LLMClient] Full message: {message}")
                        return ""

                    print(f"[LLMClient] Raw response length: {len(content)}")
                    print(f"[LLMClient] Raw response preview:\n{content[:500]}...")
                    return content

            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.NetworkError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
            ) as e:
                print(f"[LLMClient] Attempt {attempt + 1}/{max_attempts} failed: {type(e).__name__}")
                if attempt < max_attempts - 1:
                    wait_time = 4 * (2**attempt)
                    print(f"[LLMClient] Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                print(f"[LLMClient] All retries exhausted")
                raise

            except httpx.HTTPStatusError as e:
                error_text = e.response.text[:500]
                print(f"[LLMClient] API Error: {e.response.status_code} - {error_text}")

                # Auto-detect json_object not supported error (including nested in metadata.raw)
                if self.provider_id and self.supports_json_object:
                    try:
                        error_data = e.response.json()
                        raw_error = error_data.get("error", {}).get("metadata", {}).get("raw", "")
                        if "json_object is not supported" in raw_error or "json_object is not supported" in error_text:
                            print(f"[LLMClient] Detected unsupported json_object, auto-disabling and retrying...")
                            update_provider_supports_json_object(self.provider_id, False)
                            self.supports_json_object = False
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(2)
                                continue
                    except:
                        pass
                raise

        return ""

    async def close(self):
        pass


MOCK_TOOL_POOL = {}

class PersonaManager:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        self.data = {}
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def get_persona(self, persona_type: str) -> dict:
        return self.data.get(persona_type, {})

    def get_random_persona(self, language: str = "zh") -> dict:
        if not self.data:
            return {}
        
        data = self.data
        persona = {}
        
        # names -> name (string)
        if "names" in data and isinstance(data["names"], list) and data["names"]:
            persona["name"] = random.choice(data["names"])
        
        # genders -> gender (string)
        if "genders" in data and isinstance(data["genders"], list) and data["genders"]:
            gender_choice = random.choice(data["genders"])
            if isinstance(gender_choice, dict):
                persona["gender"] = gender_choice.get("name", "")
            else:
                persona["gender"] = gender_choice
        
        # personalities -> optional_tics (dict with language-specific tics) + tone
        if "personalities" in data and isinstance(data["personalities"], list) and data["personalities"]:
            personality = random.choice(data["personalities"])
            persona["tone"] = personality.get("name", "")
            persona["personality"] = personality.get("description", "")
            persona["optional_tics"] = personality.get("optional_tics", {})
        
        # identities -> race (string only, not the full identity object)
        if "identities" in data and isinstance(data["identities"], list) and data["identities"]:
            identity = random.choice(data["identities"])
            persona["race"] = identity.get("name", "")
            # Merge identity optional_tics into persona optional_tics
            identity_tics = identity.get("optional_tics", {})
            if identity_tics and persona.get("optional_tics"):
                for lang, tics in identity_tics.items():
                    if lang in persona["optional_tics"]:
                        existing = set(persona["optional_tics"][lang])
                        new_tics = [t for t in tics if t not in existing]
                        persona["optional_tics"][lang].extend(new_tics)
                    else:
                        persona["optional_tics"][lang] = tics
        
        # user_titles -> user_title (string, translated by language)
        if "user_titles" in data and isinstance(data["user_titles"], list) and data["user_titles"]:
            user_title_choice = random.choice(data["user_titles"])
            if isinstance(user_title_choice, dict):
                # 获取翻译后的称呼
                translations = user_title_choice.get("translations", {})
                persona["user_title"] = translations.get(language, user_title_choice.get("name", ""))
            else:
                persona["user_title"] = user_title_choice
        
        # Default language
        persona["language"] = language
        
        return persona

    def generate_random_persona(self, language: str = "zh") -> dict:
        return self.get_random_persona(language)

    def generate_random_user_profile(self, seed: Optional[int] = None) -> dict:
        """生成随机用户画像，部分字段可能为空"""
        if seed:
            random.seed(seed)
        
        if not self.data:
            return {}
        
        data = self.data
        profile = {}
        
        # 所有字段默认为空
        all_fields = ["name", "gender", "occupation", "location", "hobbies", "age"]
        for field in all_fields:
            if field == "hobbies":
                profile[field] = []
            else:
                profile[field] = ""
        
        # 随机决定哪些字段有值
        num_known = random.randint(1, len(all_fields))
        known_fields = random.sample(all_fields, num_known)
        
        # 填充已知字段
        if "name" in known_fields and "names" in data and data["names"]:
            profile["name"] = random.choice(data["names"])
        
        if "gender" in known_fields and "genders" in data and data["genders"]:
            gender = random.choice(data["genders"])
            if isinstance(gender, dict):
                profile["gender"] = gender.get("name", "")
            else:
                profile["gender"] = gender
        
        if "occupation" in known_fields and "occupations" in data and data["occupations"]:
            profile["occupation"] = random.choice(data["occupations"])
        
        if "location" in known_fields and "locations" in data and data["locations"]:
            profile["location"] = random.choice(data["locations"])
        
        if "hobbies" in known_fields and "hobbies" in data and data["hobbies"]:
            num_hobbies = random.randint(1, 3)
            profile["hobbies"] = random.sample(data["hobbies"], min(num_hobbies, len(data["hobbies"])))
        
        if "age" in known_fields:
            profile["age"] = str(random.randint(18, 60))
        
        return profile

    def format_user_profile(self, profile: dict) -> str:
        """Format user profile as JSON string."""
        import json
        return json.dumps(profile, ensure_ascii=False)


def normalize_language(lang_code: str) -> str:
    lang_map = {
        "zh": "zh",
        "zh-cn": "zh",
        "zh-tw": "zh",
        "en": "en",
        "en-us": "en",
        "ja": "ja",
        "ko": "ko",
        "de": "de",
        "fr": "fr",
        "es": "es",
        "ru": "ru",
    }
    return lang_map.get(lang_code.lower(), "zh")


def get_root_dir() -> Path:
    current = Path(__file__).parent
    return current.parent


def load_json_config(filename: str) -> dict:
    config_path = get_root_dir() / "data" / filename
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def extract_json_from_text(text: str) -> str:
    import re
    
    original_text = text
    text = text.strip()
    
    # 去除代码块标记
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            elif text.startswith("python"):
                text = text[6:]
        text = text.strip()
    
    # 去除常见的前缀说明
    prefixes_to_remove = [
        r'^以下是.*?[:：]\s*',
        r'^Here is.*?[:：]\s*',
        r'^Here\'s.*?[:：]\s*',
        r'^JSON.*?[:：]\s*',
        r'^Here is the.*?you requested.*?[:：]\s*',
    ]
    for prefix in prefixes_to_remove:
        text = re.sub(prefix, '', text, flags=re.IGNORECASE)
    
    # 去除行首的数字编号
    text = re.sub(r'^\d+[\.\:]\s*', '', text, flags=re.MULTILINE)
    
    # 方法1: 尝试直接解析
    if text.startswith("{") or text.startswith("["):
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
    
    # 方法2: 使用括号匹配算法提取完整的JSON
    result = _extract_json_by_bracket_matching(text)
    if result:
        return result
    
    # 方法3: 尝试用正则查找JSON数组（更保守的方式）
    result = _extract_json_array(text)
    if result:
        return result
    
    # 返回原始文本（让下游处理报错）
    return original_text


def _extract_json_by_bracket_matching(text: str) -> str:
    """使用括号匹配提取完整的JSON"""
    bracket_count = 0
    in_string = False
    escape_char = False
    start_idx = -1
    
    for i, c in enumerate(text):
        if escape_char:
            escape_char = False
            continue
        if c == '\\':
            escape_char = True
            continue
        if c == '"' and not escape_char:
            in_string = not in_string
            continue
        if in_string:
            continue
        
        if c == '[' or c == '{':
            if start_idx == -1:
                start_idx = i
            bracket_count += 1
        elif c == ']' or c == '}':
            bracket_count -= 1
            if bracket_count == 0 and start_idx >= 0:
                # 找到完整的JSON
                candidate = text[start_idx:i+1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    # 这个完整的不行，继续找
                    start_idx = -1
    
    return ""


def _extract_json_array(text: str) -> str:
    """用正则查找JSON数组，更保守的方式"""
    import re
    
    # 找所有可能的数组
    array_pattern = r'\[[\s\S]*?\]'
    matches = re.findall(array_pattern, text)
    
    for match in matches:
        # 检查是否是有效的JSON数组
        try:
            parsed = json.loads(match)
            if isinstance(parsed, list):
                return match
        except json.JSONDecodeError:
            continue
    
    return ""


def extract_response_text(text: str) -> str:
    """Extract pure response text by removing TTS instruction prefix
    
    Example: "(开心地快速说, 挥手) 说话内容" -> "说话内容"
    """
    import re
    # Remove TTS format like "(情绪+语速+语调, 动作) " or "(情绪, 动作) "
    # Pattern matches: (anything up to ) followed by optional whitespace
    pattern = r'^\([^)]+\)\s*'
    cleaned = re.sub(pattern, '', text)
    return cleaned.strip()


def generate_assistant_birthday(seed: int = None) -> str:
    if seed is not None:
        random.seed(seed)
    years = list(range(1990, 2010))
    months = list(range(1, 13))
    days = list(range(1, 28))
    year = random.choice(years)
    month = random.choice(months)
    day = random.choice(days)
    return f"{year}年{month}月{day}日"


def generate_tts_instruction_variations(n: int = 5, seed: int = None) -> list:
    """Generate random TTS instruction variations for examples"""
    if seed is not None:
        random.seed(seed)

    emotions = ["开心地", "温柔地", "难过地", "平静地", "兴奋地", "惊讶地", "悲伤地", "严肃地", "俏皮地", "尴尬地", "疲惫地"]
    speeds = ["快速说", "缓慢说", "正常说", "飞快说", "慢慢说", "从容说"]
    tones = ["说", "低语", "问", "解释", "宣布", "讨论"]
    actions = ["挥手", "点头", "摇头", "耸肩", "微笑", "皱眉", "眨眼", "鼓掌", "思考", "指向", "鞠躬", "叉腰", "抱臂", "无"]

    variations = []
    for _ in range(n):
        emotion = random.choice(emotions)
        speed = random.choice(speeds)
        tone = random.choice(tones)
        action = random.choice(actions)
        if action == "无":
            variations.append(f"({emotion}{speed}, )")
        else:
            variations.append(f"({emotion}{speed}, {action})")

    if seed is not None:
        random.seed()

    return variations
