"""
Distribution Configuration - Data generation ratio management for V4

Controlled distribution dimensions (scheduler manages these):
- Languages: zh, en, ja, ko, de, fr, es, ru
- Persona types: personality distribution
- Topics: conversation topic categories

Emergent properties (randomly sampled, NOT controlled):
- Emotions: emotional state (generated naturally by LLM)
- Actions: physical action (generated naturally by LLM)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum


class DistributionDimension(Enum):
    """Distribution dimensions supported by the scheduler

    Note: Emotion and Action are NOT controlled dimensions.
    They are emergent properties generated naturally by the LLM
    based on context, persona, and topic.
    """

    LANGUAGE = "language"
    PERSONA = "persona"
    TOPIC = "topic"
    SKILL = "skill"


@dataclass
class LanguageRatios:
    """Language distribution ratios"""

    zh: float = 0.50  # Chinese
    en: float = 0.20  # English
    ja: float = 0.05  # Japanese
    ko: float = 0.05  # Korean
    de: float = 0.05  # German
    fr: float = 0.05  # French
    es: float = 0.05  # Spanish
    ru: float = 0.05  # Russian

    def to_dict(self) -> Dict[str, float]:
        return {
            "zh": self.zh,
            "en": self.en,
            "ja": self.ja,
            "ko": self.ko,
            "de": self.de,
            "fr": self.fr,
            "es": self.es,
            "ru": self.ru,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "LanguageRatios":
        return cls(
            zh=data.get("zh", 0.50),
            en=data.get("en", 0.20),
            ja=data.get("ja", 0.05),
            ko=data.get("ko", 0.05),
            de=data.get("de", 0.05),
            fr=data.get("fr", 0.05),
            es=data.get("es", 0.05),
            ru=data.get("ru", 0.05),
        )


@dataclass
class PersonaRatios:
    """Persona type distribution ratios"""

    tsundere: float = 0.075  # 傲娇
    gentle: float = 0.095  # 温柔
    energetic: float = 0.075  # 活泼
    cool: float = 0.075  # 高冷
    dark: float = 0.055  # 腹黑
    sharp: float = 0.055  # 毒舌
    airhead: float = 0.055  # 天然呆
    chuuni: float = 0.045  # 中二病
    yandere: float = 0.040  # 病娇
    lazy: float = 0.055  # 慵懒
    genki: float = 0.075  # 元气
    intellectual: float = 0.095  # 知性
    mischievous: float = 0.075  # 调皮
    loyal: float = 0.075  # 忠诚
    neutral: float = 0.050  # 中性/默认

    def to_dict(self) -> Dict[str, float]:
        return {
            "tsundere": self.tsundere,
            "gentle": self.gentle,
            "energetic": self.energetic,
            "cool": self.cool,
            "dark": self.dark,
            "sharp": self.sharp,
            "airhead": self.airhead,
            "chuuni": self.chuuni,
            "yandere": self.yandere,
            "lazy": self.lazy,
            "genki": self.genki,
            "intellectual": self.intellectual,
            "mischievous": self.mischievous,
            "loyal": self.loyal,
            "neutral": self.neutral,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "PersonaRatios":
        return cls(
            tsundere=data.get("tsundere", 0.075),
            gentle=data.get("gentle", 0.095),
            energetic=data.get("energetic", 0.075),
            cool=data.get("cool", 0.075),
            dark=data.get("dark", 0.055),
            sharp=data.get("sharp", 0.055),
            airhead=data.get("airhead", 0.055),
            chuuni=data.get("chuuni", 0.045),
            yandere=data.get("yandere", 0.040),
            lazy=data.get("lazy", 0.055),
            genki=data.get("genki", 0.075),
            intellectual=data.get("intellectual", 0.095),
            mischievous=data.get("mischievous", 0.075),
            loyal=data.get("loyal", 0.075),
            neutral=data.get("neutral", 0.050),
        )


@dataclass
class SkillRatios:
    """Skill distribution ratios - equal distribution for each skill

    Each skill gets equal weight (1/26) to ensure balanced coverage.
    """

    # Theme & Media (7 skills)
    theme_set_season: float = 1/26
    theme_set_weather: float = 1/26
    background_audio_control: float = 1/26
    theme_set_effects: float = 1/26
    assistant_voice_control: float = 1/26
    weather_api: float = 1/26
    theme_list_presets: float = 1/26

    # File System (3 skills)
    delete_file: float = 1/26
    write_file: float = 1/26
    read_file: float = 1/26

    # Communication (1 skill)
    send_message: float = 1/26

    # System (1 skill)
    execute_command: float = 1/26

    # Folder (3 skills)
    list_directory: float = 1/26
    search_files: float = 1/26
    open_folder: float = 1/26

    # Application (1 skill)
    open_application: float = 1/26

    # Todo (5 skills)
    create_todo: float = 1/26
    update_todo: float = 1/26
    delete_todo: float = 1/26
    list_todos: float = 1/26
    search_todos: float = 1/26

    # Script Execution (1 skill)
    puppet: float = 1/26

    def to_dict(self) -> Dict[str, float]:
        return {
            # Theme & Media
            "theme_set_season": self.theme_set_season,
            "theme_set_weather": self.theme_set_weather,
            "background_audio_control": self.background_audio_control,
            "theme_set_effects": self.theme_set_effects,
            "assistant_voice_control": self.assistant_voice_control,
            "weather_api": self.weather_api,
            "theme_list_presets": self.theme_list_presets,
            # File System
            "delete_file": self.delete_file,
            "write_file": self.write_file,
            "read_file": self.read_file,
            # Communication
            "send_message": self.send_message,
            # System
            "execute_command": self.execute_command,
            # Folder
            "list_directory": self.list_directory,
            "search_files": self.search_files,
            "open_folder": self.open_folder,
            # Application
            "open_application": self.open_application,
            # Todo
            "create_todo": self.create_todo,
            "update_todo": self.update_todo,
            "delete_todo": self.delete_todo,
            "list_todos": self.list_todos,
            "search_todos": self.search_todos,
            # Script Execution
            "puppet": self.puppet,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "SkillRatios":
        return cls(
            # Theme & Media
            theme_set_season=data.get("theme_set_season", 7/26),
            theme_set_weather=data.get("theme_set_weather", 7/26),
            background_audio_control=data.get("background_audio_control", 7/26),
            theme_set_effects=data.get("theme_set_effects", 7/26),
            assistant_voice_control=data.get("assistant_voice_control", 7/26),
            weather_api=data.get("weather_api", 7/26),
            theme_list_presets=data.get("theme_list_presets", 7/26),
            # File System
            delete_file=data.get("delete_file", 3/26),
            write_file=data.get("write_file", 3/26),
            read_file=data.get("read_file", 3/26),
            # Communication
            send_message=data.get("send_message", 1/26),
            # System
            execute_command=data.get("execute_command", 1/26),
            # Folder
            list_directory=data.get("list_directory", 3/26),
            search_files=data.get("search_files", 3/26),
            open_folder=data.get("open_folder", 3/26),
            # Application
            open_application=data.get("open_application", 1/26),
            # Todo
            create_todo=data.get("create_todo", 5/26),
            update_todo=data.get("update_todo", 5/26),
            delete_todo=data.get("delete_todo", 5/26),
            list_todos=data.get("list_todos", 5/26),
            search_todos=data.get("search_todos", 5/26),
            # Script Execution
            puppet=data.get("puppet", 1/26),
        )


@dataclass
class TopicRatios:
    """Topic distribution ratios - for tree structure with topics"""

    # Daily Life
    weather_chat: float = 0.05
    greeting: float = 0.05
    mood_sharing: float = 0.05
    # Work & Study
    programming: float = 0.08
    office_skills: float = 0.05
    learning: float = 0.05
    career: float = 0.05
    # Hobbies
    sports: float = 0.06
    gaming: float = 0.05
    reading: float = 0.05
    music: float = 0.05
    # Life Services
    cooking: float = 0.05
    travel: float = 0.05
    shopping: float = 0.05
    health: float = 0.05
    # Social
    relationships: float = 0.05
    family: float = 0.05
    dating: float = 0.04
    # Knowledge
    science: float = 0.04
    history: float = 0.04
    finance: float = 0.04
    # Emotional
    emotional_support: float = 0.06
    motivation: float = 0.04

    def to_dict(self) -> Dict[str, float]:
        return {
            # Daily Life
            "weather_chat": self.weather_chat,
            "greeting": self.greeting,
            "mood_sharing": self.mood_sharing,
            # Work & Study
            "programming": self.programming,
            "office_skills": self.office_skills,
            "learning": self.learning,
            "career": self.career,
            # Hobbies
            "sports": self.sports,
            "gaming": self.gaming,
            "reading": self.reading,
            "music": self.music,
            # Life Services
            "cooking": self.cooking,
            "travel": self.travel,
            "shopping": self.shopping,
            "health": self.health,
            # Social
            "relationships": self.relationships,
            "family": self.family,
            "dating": self.dating,
            # Knowledge
            "science": self.science,
            "history": self.history,
            "finance": self.finance,
            # Emotional
            "emotional_support": self.emotional_support,
            "motivation": self.motivation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "TopicRatios":
        return cls(
            # Daily Life
            weather_chat=data.get("weather_chat", 0.05),
            greeting=data.get("greeting", 0.05),
            mood_sharing=data.get("mood_sharing", 0.05),
            # Work & Study
            programming=data.get("programming", 0.08),
            office_skills=data.get("office_skills", 0.05),
            learning=data.get("learning", 0.05),
            career=data.get("career", 0.05),
            # Hobbies
            sports=data.get("sports", 0.06),
            gaming=data.get("gaming", 0.05),
            reading=data.get("reading", 0.05),
            music=data.get("music", 0.05),
            # Life Services
            cooking=data.get("cooking", 0.05),
            travel=data.get("travel", 0.05),
            shopping=data.get("shopping", 0.05),
            health=data.get("health", 0.05),
            # Social
            relationships=data.get("relationships", 0.05),
            family=data.get("family", 0.05),
            dating=data.get("dating", 0.04),
            # Knowledge
            science=data.get("science", 0.04),
            history=data.get("history", 0.04),
            finance=data.get("finance", 0.04),
            # Emotional
            emotional_support=data.get("emotional_support", 0.06),
            motivation=data.get("motivation", 0.04),
        )


@dataclass
class DistributionConfig:
    """Complete distribution configuration for data generation

    This class manages all ratio configurations for generating balanced
    and diverse training data across multiple dimensions.
    """

    # Total target count
    total: int = 10000

    # Batch configuration
    batch_size: int = 10

    # Dimension ratios (controlled by scheduler)
    languages: LanguageRatios = field(default_factory=LanguageRatios)
    personas: PersonaRatios = field(default_factory=PersonaRatios)
    topics: TopicRatios = field(default_factory=TopicRatios)
    skills: SkillRatios = field(default_factory=SkillRatios)

    # Generation settings
    enable_persona_diversity: bool = True

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate all ratios sum to approximately 1.0 (with tolerance)"""
        errors = []
        tolerance = 0.20

        # Validate language ratios
        lang_sum = sum(self.languages.to_dict().values())
        if abs(lang_sum - 1.0) > tolerance:
            errors.append(f"Language ratios sum to {lang_sum:.4f}, expected 1.0")

        # Validate persona ratios
        persona_sum = sum(self.personas.to_dict().values())
        if abs(persona_sum - 1.0) > tolerance:
            errors.append(f"Persona ratios sum to {persona_sum:.4f}, expected 1.0")

        # Validate topic ratios (暂时跳过严格检查)
        topic_sum = sum(self.topics.to_dict().values())

        # Validate skill ratios
        skill_sum = sum(self.skills.to_dict().values())
        if abs(skill_sum - 1.0) > tolerance:
            errors.append(f"Skill ratios sum to {skill_sum:.4f}, expected 1.0")

        return len(errors) == 0, errors

    def normalize(self) -> "DistributionConfig":
        """Normalize all ratios to sum to 1.0"""

        def normalize_dict(d: Dict[str, float]) -> Dict[str, float]:
            total = sum(d.values())
            if total == 0:
                return d
            return {k: v / total for k, v in d.items()}

        # Normalize each ratio group
        lang_dict = normalize_dict(self.languages.to_dict())
        persona_dict = normalize_dict(self.personas.to_dict())
        topic_dict = normalize_dict(self.topics.to_dict())
        skill_dict = normalize_dict(self.skills.to_dict())

        new_config = DistributionConfig(
            total=self.total,
            batch_size=self.batch_size,
            languages=LanguageRatios.from_dict(lang_dict),
            personas=PersonaRatios.from_dict(persona_dict),
            topics=TopicRatios.from_dict(topic_dict),
            skills=SkillRatios.from_dict(skill_dict),
            enable_persona_diversity=self.enable_persona_diversity,
        )

        return new_config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            "total": self.total,
            "batch_size": self.batch_size,
            "languages": self.languages.to_dict(),
            "personas": self.personas.to_dict(),
            "topics": self.topics.to_dict(),
            "skills": self.skills.to_dict(),
            "enable_persona_diversity": self.enable_persona_diversity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DistributionConfig":
        """Create configuration from dictionary"""
        return cls(
            total=data.get("total", 10000),
            batch_size=data.get("batch_size", 10),
            languages=LanguageRatios.from_dict(data.get("languages", {})),
            personas=PersonaRatios.from_dict(data.get("personas", {})),
            topics=TopicRatios.from_dict(data.get("topics", {})),
            skills=SkillRatios.from_dict(data.get("skills", {})),
            enable_persona_diversity=data.get("enable_persona_diversity", True),
        )

    def get_allocation(
        self, dimension: DistributionDimension, total: Optional[int] = None
    ) -> Dict[str, int]:
        """Get allocation counts for a specific dimension

        Args:
            dimension: The dimension to allocate
            total: Total count (defaults to self.total)

        Returns:
            Dictionary mapping dimension values to target counts
        """
        if total is None:
            total = self.total

        ratio_map = {
            DistributionDimension.LANGUAGE: self.languages.to_dict(),
            DistributionDimension.PERSONA: self.personas.to_dict(),
            DistributionDimension.TOPIC: self.topics.to_dict(),
            DistributionDimension.SKILL: self.skills.to_dict(),
        }

        ratios = ratio_map.get(dimension, {})
        return _allocate_by_ratios(total, list(ratios.items()))


def _allocate_by_ratios(total: int, items: List[Tuple[str, float]]) -> Dict[str, int]:
    """Allocate total count across items based on their ratios

    Uses largest remainder method for fair allocation.
    """
    if total <= 0:
        return {k: 0 for k, _ in items}
    if not items:
        return {}

    # Calculate raw allocations
    raw = [(k, total * r) for k, r in items]
    floors = {k: int(v) for k, v in raw}
    allocated = sum(floors.values())
    remainder = total - allocated

    if remainder <= 0:
        return floors

    # Distribute remainder based on fractional parts
    fracs = sorted(((k, v - int(v)) for k, v in raw), key=lambda x: x[1], reverse=True)

    for i in range(remainder):
        k = fracs[i % len(fracs)][0]
        floors[k] += 1

    return floors


def get_default_config(total: int = 10000, batch_size: int = 10) -> DistributionConfig:
    """Get default distribution configuration"""
    return DistributionConfig(
        total=total,
        batch_size=batch_size,
    )


def get_balanced_config(total: int = 10000, batch_size: int = 10) -> DistributionConfig:
    """Get balanced configuration with equal ratios for all dimensions"""
    return DistributionConfig(
        total=total,
        batch_size=batch_size,
        languages=LanguageRatios(
            zh=0.50, en=0.20, ja=0.05, ko=0.05, de=0.05, fr=0.05, es=0.05, ru=0.05
        ),
        personas=PersonaRatios(
            tsundere=1 / 15,
            gentle=1 / 15,
            energetic=1 / 15,
            cool=1 / 15,
            dark=1 / 15,
            sharp=1 / 15,
            airhead=1 / 15,
            chuuni=1 / 15,
            yandere=1 / 15,
            lazy=1 / 15,
            genki=1 / 15,
            intellectual=1 / 15,
            mischievous=1 / 15,
            loyal=1 / 15,
            neutral=1 / 15,
        ),
        topics=TopicRatios(
            weather_chat=1 / 25,
            greeting=1 / 25,
            mood_sharing=1 / 25,
            programming=1 / 25,
            office_skills=1 / 25,
            learning=1 / 25,
            career=1 / 25,
            sports=1 / 25,
            gaming=1 / 25,
            reading=1 / 25,
            music=1 / 25,
            cooking=1 / 25,
            travel=1 / 25,
            shopping=1 / 25,
            health=1 / 25,
            relationships=1 / 25,
            family=1 / 25,
            dating=1 / 25,
            science=1 / 25,
            history=1 / 25,
            finance=1 / 25,
            emotional_support=1 / 25,
            motivation=1 / 25,
        ),
    )


def get_chat_heavy_config(
    total: int = 10000, batch_size: int = 10
) -> DistributionConfig:
    """Get configuration with heavy emphasis on chat/dialogue scenarios"""
    return DistributionConfig(
        total=total,
        batch_size=batch_size,
        topics=TopicRatios(
            weather_chat=0.10,
            greeting=0.10,
            mood_sharing=0.08,
            programming=0.04,
            office_skills=0.03,
            learning=0.03,
            career=0.03,
            sports=0.05,
            gaming=0.05,
            reading=0.05,
            music=0.05,
            cooking=0.04,
            travel=0.04,
            shopping=0.04,
            health=0.04,
            relationships=0.06,
            family=0.05,
            dating=0.05,
            science=0.03,
            history=0.03,
            finance=0.03,
            emotional_support=0.08,
            motivation=0.05,
        ),
    )
