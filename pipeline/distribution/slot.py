"""
Slot System - Distribution dimension tracking for V4

Each slot represents a unique combination of distribution dimensions:
- Language: zh, en, ja, ko, de, fr, es, ru
- Persona: personality type
- Topic: conversation category
- Emotion: emotional state
- Action: physical action
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class Language(Enum):
    """Supported languages"""

    ZH = "zh"  # Chinese
    EN = "en"  # English
    JA = "ja"  # Japanese
    KO = "ko"  # Korean
    DE = "de"  # German
    FR = "fr"  # French
    ES = "es"  # Spanish
    RU = "ru"  # Russian


class PersonaType(Enum):
    """Personality types"""

    TSUNDERE = "tsundere"  # 傲娇
    GENTLE = "gentle"  # 温柔
    ENERGETIC = "energetic"  # 活泼
    COOL = "cool"  # 高冷
    DARK = "dark"  # 腹黑
    SHARP = "sharp"  # 毒舌
    AIRHEAD = "airhead"  # 天然呆
    CHUUNI = "chuuni"  # 中二病
    YANDERE = "yandere"  # 病娇
    LAZY = "lazy"  # 慵懒
    GENKI = "genki"  # 元气
    INTELLECTUAL = "intellectual"  # 知性
    MISCHIEVOUS = "mischievous"  # 调皮
    LOYAL = "loyal"  # 忠诚
    NEUTRAL = "neutral"  # 中性


class TopicCategory(Enum):
    """Conversation topic categories - Supports both legacy enums and dynamic categories from config"""

    DAILY_CHAT = "daily_chat"  # 日常闲聊
    TASK_HELP = "task_help"  # 任务协助
    EMOTIONAL_SUPPORT = "emotional_support"  # 情感陪伴
    CREATIVE_WRITING = "creative_writing"  # 创作写作
    KNOWLEDGE_QA = "knowledge_qa"  # 知识问答
    TOOL_USAGE = "tool_usage"  # 工具使用
    MULTI_STEP_TASK = "multi_step_task"  # 多步骤任务
    ERROR_HANDLING = "error_handling"  # 错误处理

    @classmethod
    def _missing_(cls, value):
        """Support dynamic categories from chat_topics.json"""
        if isinstance(value, str):
            # Create a new member dynamically
            try:
                member = object.__new__(cls)
                member._name_ = value
                member._value_ = value
                return member
            except Exception:
                pass
        return None

    @classmethod
    def from_string(cls, value: str):
        """Create TopicCategory from string, supporting dynamic values"""
        try:
            return cls(value)
        except ValueError:
            # Dynamic category not in enum
            member = object.__new__(cls)
            member._name_ = value
            member._value_ = value
            return member


class Skill(Enum):
    """Skill types - 26 skills with aliases"""

    # Theme & Media
    THEME_SET_SEASON = "theme_set_season"
    THEME_SET_WEATHER = "theme_set_weather"
    BACKGROUND_AUDIO_CONTROL = "background_audio_control"
    THEME_SET_EFFECTS = "theme_set_effects"
    ASSISTANT_VOICE_CONTROL = "assistant_voice_control"
    WEATHER_API = "weather_api"
    THEME_LIST_PRESETS = "theme_list_presets"

    # File System
    DELETE_FILE = "delete_file"
    WRITE_FILE = "write_file"
    READ_FILE = "read_file"

    # Communication
    SEND_MESSAGE = "send_message"

    # System
    EXECUTE_COMMAND = "execute_command"

    # Folder
    LIST_DIRECTORY = "list_directory"
    SEARCH_FILES = "search_files"
    OPEN_FOLDER = "open_folder"

    # Application
    OPEN_APPLICATION = "open_application"

    # Todo
    CREATE_TODO = "create_todo"
    UPDATE_TODO = "update_todo"
    DELETE_TODO = "delete_todo"
    LIST_TODOS = "list_todos"
    SEARCH_TODOS = "search_todos"

    # Script Execution
    PUPPET = "puppet"

    @classmethod
    def _missing_(cls, value):
        """Support dynamic skill names"""
        if isinstance(value, str):
            try:
                member = object.__new__(cls)
                member._name_ = value
                member._value_ = value
                return member
            except Exception:
                pass
        return None

    @classmethod
    def from_string(cls, value: str):
        """Create Skill from string, supporting dynamic values"""
        try:
            return cls(value)
        except ValueError:
            member = object.__new__(cls)
            member._name_ = value
            member._value_ = value
            return member


class Emotion(Enum):
    """Emotional states"""

    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SURPRISED = "surprised"
    NEUTRAL = "neutral"
    SERIOUS = "serious"
    CONFUSED = "confused"
    SHY = "shy"
    EXCITED = "excited"
    CALM = "calm"


class Action(Enum):
    """Physical actions"""

    NILL = "nill"  # No action
    SMILE = "smile"
    LAUGH = "laugh"
    NOD = "nod"
    SHAKE_HEAD = "shake_head"
    WAVE = "wave"
    FROWN = "frown"
    SIGH = "sigh"
    THINK = "think"
    OBSERVE = "observe"
    CLENCH_FIST = "clench_fist"
    SPREAD_HANDS = "spread_hands"
    BOW = "bow"
    CLAP = "clap"
    TILT_HEAD = "tilt_head"
    POINT = "point"
    SHRUG = "shrug"
    AKIMBO = "akimbo"
    THUMBS_UP = "thumbs_up"


@dataclass
class SlotType:
    """Slot type definition - uniquely identifies a distribution slot

    A slot type represents a specific combination of distribution dimensions.
    Multiple slots can share the same type but have different targets.
    """

    language: Language = Language.ZH
    persona: PersonaType = PersonaType.NEUTRAL
    topic: TopicCategory = TopicCategory.DAILY_CHAT
    skill: Skill = Skill.THEME_SET_SEASON
    emotion: Emotion = Emotion.NEUTRAL
    action: Action = Action.NILL

    @property
    def id(self) -> str:
        """Generate unique identifier for this slot type"""
        parts = [
            self.language.value,
            self.persona.value,
            self.topic.value,
            self.skill.value,
            self.emotion.value,
            self.action.value,
        ]

        return "_".join(parts)

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SlotType):
            return NotImplemented
        return self.id == other.id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "language": self.language.value,
            "persona": self.persona.value,
            "topic": self.topic.value,
            "skill": self.skill.value,
            "emotion": self.emotion.value,
            "action": self.action.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlotType":
        """Create from dictionary representation"""
        return cls(
            language=Language(data.get("language", "zh")),
            persona=PersonaType(data.get("persona", "neutral")),
            topic=TopicCategory(data.get("topic", "daily_chat")),
            skill=Skill(data.get("skill", "theme_set_season")),
            emotion=Emotion(data.get("emotion", "neutral")),
            action=Action(data.get("action", "nill")),
        )


@dataclass
class Slot:
    """Distribution slot with target and progress tracking

    Each slot tracks:
    - target: Total number of items to generate
    - completed: Successfully generated items
    - failed: Failed generation attempts
    - reserved: Number of items currently being processed (not yet completed/failed)
    - slot_type: The type of this slot (defines the distribution dimensions)
    """

    slot_type: SlotType
    target: int
    completed: int = 0
    failed: int = 0
    reserved: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Unique identifier for this slot"""
        return self.slot_type.id

    @property
    def remaining(self) -> int:
        """Number of items remaining to reach target (excluding reserved)"""
        return max(0, self.target - (self.completed + self.failed + self.reserved))

    @property
    def progress(self) -> float:
        """Progress ratio (0.0 to 1.0)"""
        if self.target == 0:
            return 1.0
        return (self.completed + self.failed + self.reserved) / self.target

    @property
    def success_rate(self) -> float:
        """Success rate of generation attempts"""
        total = self.completed + self.failed
        if total == 0:
            return 1.0
        return self.completed / total

    @property
    def is_complete(self) -> bool:
        """Whether this slot has reached its target"""
        return self.remaining == 0

    @property
    def is_under_represented(self) -> bool:
        """Whether this slot is under-represented compared to target"""
        if self.target == 0:
            return False
        return self.progress < 0.8  # Less than 80% complete

    def reserve(self, count: int = 1):
        """Reserve slots for processing"""
        available = self.target - (self.completed + self.failed + self.reserved)
        actual = min(count, available)
        self.reserved += actual
        return actual

    def record_success(self, count: int = 1):
        """Record successful generation"""
        self.completed += count
        if self.reserved > 0:
            self.reserved -= count

    def record_failure(self, count: int = 1):
        """Record failed generation"""
        self.failed += count
        if self.reserved > 0:
            self.reserved -= count

    def unreserve(self, count: int = 1):
        """Cancel a reservation (e.g., on error)"""
        self.reserved = max(0, self.reserved - count)

    def reset(self):
        """Reset progress tracking"""
        self.completed = 0
        self.failed = 0

    def adjust_target(self, new_target: int):
        """Adjust the target count"""
        self.target = new_target

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": self.id,
            "slot_type": self.slot_type.to_dict(),
            "target": self.target,
            "completed": self.completed,
            "failed": self.failed,
            "reserved": self.reserved,
            "remaining": self.remaining,
            "progress": self.progress,
            "success_rate": self.success_rate,
            "is_complete": self.is_complete,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Slot":
        """Create from dictionary representation"""
        slot = cls(
            slot_type=SlotType.from_dict(data["slot_type"]),
            target=data["target"],
            completed=data.get("completed", 0),
            failed=data.get("failed", 0),
            reserved=data.get("reserved", 0),
            metadata=data.get("metadata", {}),
        )
        return slot


def create_slot(
    target: int,
    language: str = "zh",
    persona: str = "neutral",
    topic: str = "daily_chat",
    skill: str = "theme_set_season",
    emotion: str = "neutral",
    action: str = "nill",
) -> Slot:
    """Convenience function to create a slot

    Args:
        target: Target count for this slot
        language: Language code (zh, en, ja, etc.)
        persona: Persona type
        topic: Topic category
        skill: Skill type
        emotion: Emotional state
        action: Physical action

    Returns:
        Configured Slot instance
    """
    slot_type = SlotType(
        language=Language(language),
        persona=PersonaType(persona),
        topic=TopicCategory(topic),
        skill=Skill(skill),
        emotion=Emotion(emotion),
        action=Action(action),
    )

    return Slot(slot_type=slot_type, target=target)


def filter_slots_by_language(slots: List[Slot], language: Language) -> List[Slot]:
    """Filter slots by language"""
    return [s for s in slots if s.slot_type.language == language]


def filter_slots_by_persona(slots: List[Slot], persona: PersonaType) -> List[Slot]:
    """Filter slots by persona type"""
    return [s for s in slots if s.slot_type.persona == persona]


def filter_slots_by_topic(slots: List[Slot], topic: TopicCategory) -> List[Slot]:
    """Filter slots by topic category"""
    return [s for s in slots if s.slot_type.topic == topic]


def filter_slots_by_skill(slots: List[Slot], skill: Skill) -> List[Slot]:
    """Filter slots by skill type"""
    return [s for s in slots if s.slot_type.skill == skill]


def filter_incomplete_slots(slots: List[Slot]) -> List[Slot]:
    """Filter to only incomplete slots"""
    return [s for s in slots if not s.is_complete]


def get_slots_summary(slots: List[Slot]) -> Dict[str, Any]:
    """Get summary statistics for a list of slots"""
    total_target = sum(s.target for s in slots)
    total_completed = sum(s.completed for s in slots)
    total_failed = sum(s.failed for s in slots)

    # Count by language
    by_language = {}
    for lang in Language:
        lang_slots = filter_slots_by_language(slots, lang)
        by_language[lang.value] = {
            "target": sum(s.target for s in lang_slots),
            "completed": sum(s.completed for s in lang_slots),
            "failed": sum(s.failed for s in lang_slots),
        }

    return {
        "total_target": total_target,
        "total_completed": total_completed,
        "total_failed": total_failed,
        "total_remaining": total_target - total_completed - total_failed,
        "overall_progress": total_completed / total_target if total_target > 0 else 1.0,
        "by_language": by_language,
        "incomplete_count": len(filter_incomplete_slots(slots)),
    }
