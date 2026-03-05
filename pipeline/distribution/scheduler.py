"""
Layered Batch Scheduler - V4 Distribution Scheduler

Core features:
1. Task-based architecture with persistent storage support
2. Slot-based distribution across multiple dimensions
3. Dynamic balancing to maintain configured ratios
4. Weighted sampling prioritizing under-represented categories
5. Integration with V4's TaskManager for progress tracking
"""

import random
import json
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, Callable
from pathlib import Path
from datetime import datetime

from .slot import (
    Slot,
    SlotType,
    Language,
    PersonaType,
    TopicCategory,
    Skill,
    Emotion,
    Action,
    create_slot,
    filter_incomplete_slots,
    get_slots_summary,
    filter_slots_by_skill,
)
from .config import (
    DistributionConfig,
    DistributionDimension,
    LanguageRatios,
    PersonaRatios,
    TopicRatios,
    _allocate_by_ratios,
    get_default_config,
)


@dataclass
class BatchItem:
    """Individual generation task within a batch

    Each batch item contains all parameters needed for generation,
    derived from its assigned slot.
    """

    slot_id: str
    language: str
    persona: str
    topic: str
    skill: str
    emotion: str
    action: str
    priority: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "slot_id": self.slot_id,
            "language": self.language,
            "persona": self.persona,
            "topic": self.topic,
            "skill": self.skill,
            "emotion": self.emotion,
            "action": self.action,
            "priority": self.priority,
            "metadata": self.metadata,
        }

    @classmethod
    def from_slot(cls, slot: Slot, priority: float = 1.0) -> "BatchItem":
        """Create a BatchItem from a Slot"""
        st = slot.slot_type
        return cls(
            slot_id=slot.id,
            language=st.language.value,
            persona=st.persona.value,
            topic=st.topic.value,
            skill=st.skill.value,
            emotion=st.emotion.value,
            action=st.action.value,
            priority=priority,
        )


@dataclass
class SchedulerState:
    """Persistent scheduler state for resumable generation"""

    config: DistributionConfig
    slots: List[Slot]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "config": self.config.to_dict(),
            "slots": [s.to_dict() for s in self.slots],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SchedulerState":
        """Create state from dictionary"""
        return cls(
            config=DistributionConfig.from_dict(data["config"]),
            slots=[Slot.from_dict(s) for s in data.get("slots", [])],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            version=data.get("version", "1.0"),
        )

    def save(self, path: Path):
        """Save state to file"""
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "SchedulerState":
        """Load state from file"""
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


class LayeredBatchScheduler:
    """Layered batch scheduler for V4 data generation

    Manages distribution of generation tasks across multiple dimensions
    while maintaining configured ratios and prioritizing under-represented
    categories.

    Key features:
    - Slot-based distribution tracking
    - Dynamic ratio balancing
    - Weighted sampling for priority
    - Persistent state for resumable generation
    - Progress tracking and reporting
    """

    def __init__(
        self,
        config: Optional[DistributionConfig] = None,
        state_path: Optional[Path] = None,
        seed: Optional[int] = None,
        selected_topics: Optional[List[str]] = None,
    ):
        """Initialize the scheduler

        Args:
            config: Distribution configuration (uses default if None)
            state_path: Path to load/save persistent state
            seed: Random seed for reproducibility
            selected_topics: List of topic categories to include (None means all)
        """
        self.config = config or get_default_config()
        self.state_path = state_path
        self.seed = seed
        self.selected_topics = selected_topics
        self.rng = random.Random(seed)
        
        # Thread lock for concurrent access
        self._lock = threading.Lock()

        # Initialize or load state
        if state_path and state_path.exists():
            self._load_state()
        else:
            self._init_state()

        # Build slot lookup map for fast access
        self._rebuild_slot_map()

    def _init_state(self):
        """Initialize fresh state from configuration"""
        self.state = SchedulerState(
            config=self.config,
            slots=self._build_slots_from_config(),
        )

    def _load_state(self):
        """Load state from persistent storage"""
        if self.state_path:
            self.state = SchedulerState.load(self.state_path)
            self.config = self.state.config

    def _save_state(self):
        """Save state to persistent storage"""
        if self.state_path:
            self.state.updated_at = datetime.now().isoformat()
            self.state.save(self.state_path)

    def save_state(self, path: str = None) -> None:
        """Public method to save state to a file path"""
        if path:
            self.state.updated_at = datetime.now().isoformat()
            self.state.save(Path(path))
        else:
            self._save_state()

    def load_state(self, path: str) -> None:
        """Public method to load state from a file path"""
        self.state = SchedulerState.load(Path(path))
        self.config = self.state.config
        self._rebuild_slot_map()

    def _rebuild_slot_map(self):
        """Rebuild slot lookup map"""
        self._slot_map = {s.id: s for s in self.state.slots}

    def _build_slots_from_config(self) -> List[Slot]:
        """Build all slots from configuration using ratio allocation"""
        slots = []
        total = self.config.total

        # Get language allocation
        lang_alloc = self._get_dimension_allocation(
            DistributionDimension.LANGUAGE, total
        )

        for lang, lang_count in lang_alloc.items():
            if lang_count <= 0:
                continue

            slots.extend(
                self._create_slots(
                    language=lang,
                    count=lang_count,
                )
            )

        return slots

    def _get_dimension_allocation(
        self,
        dimension: DistributionDimension,
        total: int,
    ) -> Dict[str, int]:
        """Get allocation for a dimension based on configuration"""
        return self.config.get_allocation(dimension, total)

    def _create_slots(
        self,
        language: str,
        count: int,
    ) -> List[Slot]:
        """Create slots for a specific language configuration"""
        slots = []

        # Get persona allocation
        persona_alloc = self._get_dimension_allocation(
            DistributionDimension.PERSONA, count
        )

        # Handle selected_topics - if provided, use them directly instead of TopicRatios
        if self.selected_topics is not None and len(self.selected_topics) > 0:
            # selected_topics format: "category_level" (e.g., "主题氛围_L0")
            # Distribute evenly across selected topics
            topic_alloc = {t: count // len(self.selected_topics) for t in self.selected_topics}
            # Give remaining to first topic
            remaining = count - sum(topic_alloc.values())
            if remaining > 0:
                first_topic = list(topic_alloc.keys())[0]
                topic_alloc[first_topic] += remaining
            
            # Get skill categories from topics and filter skills
            import json
            from pathlib import Path
            topics_config_path = Path(__file__).parent.parent / "data" / "chat_topics.json"
            skill_categories_map = {}
            topics_data = {}
            if topics_config_path.exists():
                with open(topics_config_path, "r", encoding="utf-8") as f:
                    topics_data = json.load(f)
                    skill_categories_map = topics_data.get("skill_categories", {})
            
            # Collect all skills from selected topic categories
            allowed_skills = set()
            for topic_key in self.selected_topics:
                # topic_key format: "category_level", extract category
                category = topic_key.rsplit("_", 1)[0] if "_" in topic_key else topic_key
                # Find the topic in config
                for topic in topics_data.get("topics", []):
                    if topic.get("category") == category:
                        for cat in topic.get("suitable_skill_categories", []):
                            allowed_skills.update(skill_categories_map.get(cat, []))
            
            # Filter skill allocation
            all_skill_alloc = self._get_dimension_allocation(DistributionDimension.SKILL, count)
            if allowed_skills:
                skill_alloc = {k: v for k, v in all_skill_alloc.items() if k in allowed_skills}
                # Redistribute to ensure total equals count
                if skill_alloc:
                    total = sum(skill_alloc.values())
                    if total > 0:
                        scale = count / total
                        skill_alloc = {k: int(v * scale) for k, v in skill_alloc.items()}
            else:
                skill_alloc = all_skill_alloc
        else:
            # Use TopicRatios allocation
            topic_alloc = self._get_dimension_allocation(DistributionDimension.TOPIC, count)
            skill_alloc = self._get_dimension_allocation(DistributionDimension.SKILL, count)

        if not topic_alloc:
            return []

        # Build combinations with weights
        combos = []
        for persona, p_count in persona_alloc.items():
            if p_count <= 0:
                continue
            for topic, t_count in topic_alloc.items():
                if t_count <= 0:
                    continue
                for skill, s_count in skill_alloc.items():
                    if s_count <= 0:
                        continue
                    combos.append({
                        "persona": persona,
                        "topic": topic,
                        "skill": skill,
                        "weight": p_count * t_count * s_count,
                    })

        if not combos:
            return []

        # Distribute count proportionally
        total_weight = sum(c["weight"] for c in combos)
        if total_weight == 0:
            return []

        remaining = count
        for i, combo in enumerate(combos):
            if remaining <= 0:
                break

            # Last combo gets remaining
            if i == len(combos) - 1:
                target = remaining
            else:
                target = max(1, int(count * combo["weight"] / total_weight))
                target = min(target, remaining)

            if target <= 0:
                continue

            remaining -= target

            # Sample emotion and action
            emotion = self._sample_emotion()
            action = self._sample_action()

            slot = create_slot(
                language=language,
                persona=combo["persona"],
                topic=combo["topic"],
                skill=combo["skill"],
                emotion=emotion,
                action=action,
                target=target,
            )

            slots.append(slot)

        return slots

    def _sample_emotion(self) -> str:
        """Sample an emotion randomly (not controlled distribution)

        Emotions are emergent properties based on context, not controlled.
        """
        emotions = [
            "happy",
            "sad",
            "angry",
            "surprised",
            "neutral",
            "serious",
            "confused",
            "shy",
            "excited",
            "calm",
        ]
        return self.rng.choice(emotions)

    def _sample_action(self) -> str:
        """Sample an action randomly (not controlled distribution)

        Actions are emergent properties based on context, not controlled.
        """
        actions = [
            "nill",
            "smile",
            "laugh",
            "nod",
            "shake_head",
            "wave",
            "frown",
            "sigh",
            "think",
            "observe",
            "clench_fist",
            "spread_hands",
            "bow",
            "clap",
            "tilt_head",
            "point",
            "shrug",
            "akimbo",
            "thumbs_up",
        ]
        return self.rng.choice(actions)

    def _weighted_choice(self, weights: Dict[str, float]) -> str:
        """Make a weighted random choice from options"""
        items = list(weights.items())
        total = sum(w for _, w in items)

        if total == 0:
            return items[0][0] if items else ""

        r = self.rng.uniform(0, total)
        cumulative = 0

        for item, weight in items:
            cumulative += weight
            if r <= cumulative:
                return item

        return items[-1][0] if items else ""

    @property
    def slots(self) -> List[Slot]:
        """Get all slots"""
        return self.state.slots

    @property
    def total_target(self) -> int:
        """Total target count across all slots"""
        return sum(s.target for s in self.state.slots)

    @property
    def total_completed(self) -> int:
        """Total completed count across all slots"""
        return sum(s.completed for s in self.state.slots)

    @property
    def total_failed(self) -> int:
        """Total failed count across all slots"""
        return sum(s.failed for s in self.state.slots)

    @property
    def total_remaining(self) -> int:
        """Total remaining count across all slots"""
        return sum(s.remaining for s in self.state.slots)

    @property
    def overall_progress(self) -> float:
        """Overall completion progress (0.0 to 1.0)"""
        target = self.total_target
        if target == 0:
            return 1.0
        return self.total_completed / target

    @property
    def is_complete(self) -> bool:
        """Whether all slots are complete"""
        return all(s.is_complete for s in self.state.slots)

    def get_slot(self, slot_id: str) -> Optional[Slot]:
        """Get a slot by ID"""
        return self._slot_map.get(slot_id)

    def get_incomplete_slots(self) -> List[Slot]:
        """Get all incomplete slots"""
        return filter_incomplete_slots(self.state.slots)

    def next_batch(
        self,
        batch_size: int,
        strategy: str = "balanced",
    ) -> List[BatchItem]:
        """Get the next batch of generation tasks (thread-safe)

        Args:
            batch_size: Number of items to generate
            strategy: Selection strategy - "balanced", "progress", "random"

        Returns:
            List of BatchItem objects
        """
        with self._lock:
            candidates = self.get_incomplete_slots()

            if not candidates:
                return []

            # Select items based on strategy
            if strategy == "progress":
                items = self._select_by_progress(candidates, batch_size)
            elif strategy == "random":
                items = self._select_randomly(candidates, batch_size)
            else:  # balanced
                items = self._select_balanced(candidates, batch_size)

            # Reserve slots for selected items
            for item in items:
                slot = self.get_slot(item.slot_id)
                if slot:
                    slot.reserve(1)

            return items

    def _select_by_progress(
        self,
        candidates: List[Slot],
        batch_size: int,
    ) -> List[BatchItem]:
        """Select items prioritizing slots with lowest progress"""
        # Sort by progress (ascending)
        sorted_slots = sorted(candidates, key=lambda s: s.progress)

        items = []
        for slot in sorted_slots:
            if len(items) >= batch_size:
                break

            # Calculate priority based on under-representation
            priority = 1.0 - slot.progress

            # Add items for this slot
            remaining = min(slot.remaining, batch_size - len(items))
            for _ in range(remaining):
                items.append(BatchItem.from_slot(slot, priority))

        return items

    def _select_randomly(
        self,
        candidates: List[Slot],
        batch_size: int,
    ) -> List[BatchItem]:
        """Select items randomly from candidates"""
        # Weight by remaining count
        weights = [s.remaining for s in candidates]
        total_weight = sum(weights)

        if total_weight == 0:
            return []

        items = []
        selected_counts = {s.id: 0 for s in candidates}

        while len(items) < batch_size:
            # Select slot weighted by remaining
            slot = self.rng.choices(
                candidates,
                weights=[s.remaining - selected_counts[s.id] for s in candidates],
                k=1,
            )[0]

            if selected_counts[slot.id] < slot.remaining:
                items.append(BatchItem.from_slot(slot, 1.0))
                selected_counts[slot.id] += 1

            # Check if all slots exhausted
            if all(selected_counts[s.id] >= s.remaining for s in candidates):
                break

        return items

    def _select_balanced(
        self,
        candidates: List[Slot],
        batch_size: int,
    ) -> List[BatchItem]:
        """Select items balancing progress across all dimensions"""
        if not candidates:
            return []

        # Group slots by language for balanced selection
        by_language: Dict[str, List[Slot]] = {}
        for slot in candidates:
            lang = slot.slot_type.language.value
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(slot)

        # Calculate weights per language based on remaining
        total_remaining = sum(s.remaining for s in candidates)
        lang_weights = {}
        for lang, slots in by_language.items():
            lang_remaining = sum(s.remaining for s in slots)
            lang_weights[lang] = lang_remaining / total_remaining if total_remaining > 0 else 0

        # Sort slots by progress within each language
        for lang, slots in by_language.items():
            slots.sort(key=lambda s: s.progress)

        items = []
        lang_indices = {lang: 0 for lang in by_language}

        # Select items using weighted round-robin
        while len(items) < batch_size:
            # Select language by weight
            langs = list(lang_weights.keys())
            weights = [lang_weights[l] for l in langs]
            
            if not langs or sum(weights) == 0:
                break

            selected_lang = self.rng.choices(langs, weights=weights, k=1)[0]
            slots = by_language[selected_lang]
            idx = lang_indices[selected_lang]

            # Find next available slot
            while idx < len(slots):
                slot = slots[idx]
                if slot.remaining > 0:
                    priority = 1.0 + (1.0 - slot.progress)
                    items.append(BatchItem.from_slot(slot, priority))
                    lang_indices[selected_lang] = idx + 1
                    break
                idx += 1
            else:
                # All slots exhausted for this language
                lang_weights[selected_lang] = 0

            if len(items) >= batch_size:
                break

        # Shuffle to avoid patterns
        self.rng.shuffle(items)

        return items[:batch_size]

    def next_batch_by_ratio(
        self,
        batch_size: int,
        dimension: DistributionDimension = DistributionDimension.LANGUAGE,
    ) -> List[BatchItem]:
        """Get batch ensuring representation across a specific dimension

        This method ensures that the batch maintains the configured ratios
        for the specified dimension, giving priority to under-represented
        categories.

        Args:
            batch_size: Number of items to generate
            dimension: Dimension to balance (language, persona, topic)

        Returns:
            List of BatchItem objects
        """
        candidates = self.get_incomplete_slots()

        if not candidates:
            return []

        # Group slots by dimension value
        groups: Dict[str, List[Slot]] = {}
        for slot in candidates:
            value = self._get_slot_dimension_value(slot, dimension)
            if value not in groups:
                groups[value] = []
            groups[value].append(slot)

        # Calculate target allocation for this batch
        total_remaining = sum(s.remaining for s in candidates)
        batch_allocations = {}

        for value, slots in groups.items():
            group_remaining = sum(s.remaining for s in slots)
            ratio = group_remaining / total_remaining if total_remaining > 0 else 0
            batch_allocations[value] = max(1, int(batch_size * ratio))

        # Select items from each group
        items = []
        for value, target_count in batch_allocations.items():
            if len(items) >= batch_size:
                break

            group_slots = groups[value]
            actual_count = min(target_count, batch_size - len(items))

            # Select from slots with lowest progress first
            sorted_slots = sorted(group_slots, key=lambda s: s.progress)

            for slot in sorted_slots:
                if actual_count <= 0:
                    break

                take = min(actual_count, slot.remaining)
                priority = 1.0 + (1.0 - slot.progress)

                for _ in range(take):
                    items.append(BatchItem.from_slot(slot, priority))

                actual_count -= take

        # Shuffle results
        self.rng.shuffle(items)

        return items[:batch_size]

    def _get_slot_dimension_value(
        self, slot: Slot, dimension: DistributionDimension
    ) -> str:
        """Get the value of a slot for a specific dimension"""
        st = slot.slot_type
        dimension_map = {
            DistributionDimension.LANGUAGE: st.language.value,
            DistributionDimension.PERSONA: st.persona.value,
            DistributionDimension.TOPIC: st.topic.value,
            DistributionDimension.SKILL: st.skill.value,
        }
        return dimension_map.get(dimension, "unknown")

    def record_result(self, slot_id: str, success: bool, count: int = 1):
        """Record generation result for a slot (thread-safe)

        Args:
            slot_id: ID of the slot
            success: Whether generation was successful
            count: Number of items (default 1)
        """
        with self._lock:
            slot = self.get_slot(slot_id)
            if slot:
                if success:
                    slot.record_success(count)
                else:
                    slot.record_failure(count)

            # Save state periodically
            if (self.total_completed + self.total_failed) % 100 == 0:
                self._save_state()

    def record_batch_results(self, results: List[Tuple[str, bool]]):
        """Record results for a batch of items

        Args:
            results: List of (slot_id, success) tuples
        """
        for slot_id, success in results:
            self.record_result(slot_id, success)

        # Save state after batch
        self._save_state()

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive scheduler status

        Returns:
            Dictionary with status information
        """
        summary = get_slots_summary(self.state.slots)

        return {
            "config": {
                "total": self.config.total,
                "batch_size": self.config.batch_size,
            },
            "progress": {
                "target": self.total_target,
                "completed": self.total_completed,
                "failed": self.total_failed,
                "remaining": self.total_remaining,
                "progress_ratio": self.overall_progress,
                "is_complete": self.is_complete,
            },
            "breakdown": summary,
            "by_language": self._get_language_status(),
            "by_skill": self._get_skill_status(),
            "timestamp": datetime.now().isoformat(),
        }

    def _get_language_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status broken down by language"""
        status = {}
        for lang in Language:
            slots = [s for s in self.state.slots if s.slot_type.language == lang]
            if slots:
                status[lang.value] = {
                    "target": sum(s.target for s in slots),
                    "completed": sum(s.completed for s in slots),
                    "failed": sum(s.failed for s in slots),
                }
        return status

    def _get_skill_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status broken down by skill"""
        status = {}
        for skill in Skill:
            slots = [s for s in self.state.slots if s.slot_type.skill == skill]
            if slots:
                status[skill.value] = {
                    "target": sum(s.target for s in slots),
                    "completed": sum(s.completed for s in slots),
                    "failed": sum(s.failed for s in slots),
                }
        return status

    def get_under_represented_slots(
        self,
        threshold: float = 0.8,
        limit: int = 10,
    ) -> List[Slot]:
        """Get slots that are under-represented

        Args:
            threshold: Progress threshold (slots below this are under-represented)
            limit: Maximum number of slots to return

        Returns:
            List of under-represented slots
        """
        incomplete = self.get_incomplete_slots()
        under_represented = [s for s in incomplete if s.progress < threshold]

        # Sort by progress (ascending)
        under_represented.sort(key=lambda s: s.progress)

        return under_represented[:limit]

    def adjust_for_completion_rate(self):
        """Dynamically adjust targets based on completion rates

        If certain slots have consistently low success rates, this method
        can increase their targets to compensate.
        """
        for slot in self.state.slots:
            if slot.success_rate < 0.5 and slot.target > 0:
                # Increase target to compensate for failures
                new_target = int(slot.target / max(0.3, slot.success_rate))
                slot.adjust_target(new_target)

        self._save_state()

    def reset(self):
        """Reset all progress tracking"""
        for slot in self.state.slots:
            slot.reset()

        self._save_state()

    def export_progress(self, path: Path):
        """Export progress report to file"""
        status = self.get_status()
        path.write_text(
            json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def create_scheduler(
    total: int = 10000,
    batch_size: int = 10,
    config: Optional[DistributionConfig] = None,
    state_path: Optional[Path] = None,
    seed: Optional[int] = None,
) -> LayeredBatchScheduler:
    """Convenience function to create a scheduler

    Args:
        total: Total target count
        batch_size: Default batch size
        config: Optional custom configuration
        state_path: Path for persistent state
        seed: Random seed

    Returns:
        Configured LayeredBatchScheduler instance
    """
    if config is None:
        config = get_default_config(total=total, batch_size=batch_size)
    else:
        config.total = total
        config.batch_size = batch_size

    return LayeredBatchScheduler(
        config=config,
        state_path=state_path,
        seed=seed,
    )
