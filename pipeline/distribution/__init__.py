"""
V4 Distribution Scheduler - Balanced data generation across multiple dimensions

This module provides comprehensive distribution scheduling for V4 data generation,
supporting balanced allocation across languages, personas, topics,
emotions, and actions.

Key Components:
- DistributionConfig: Complete ratio configuration for all dimensions
- Slot: Individual distribution slot with progress tracking
- LayeredBatchScheduler: Main scheduler with persistent state support

Usage:
    from pipeline.distribution import (
        LayeredBatchScheduler,
        DistributionConfig,
        get_default_config,
    )

    # Create scheduler
    config = get_default_config(total=10000)
    scheduler = LayeredBatchScheduler(config=config)

    # Get next batch
    batch = scheduler.next_batch(batch_size=10)

    # Record results
    scheduler.record_batch_results([
        (item.slot_id, True),   # Success
        (item.slot_id, False),  # Failure
    ])

    # Check status
    status = scheduler.get_status()
"""

# Configuration
from .config import (
    DistributionConfig,
    DistributionDimension,
    LanguageRatios,
    PersonaRatios,
    TopicRatios,
    get_default_config,
    get_balanced_config,
    get_chat_heavy_config,
)

# Slot System
from .slot import (
    Slot,
    SlotType,
    Language,
    PersonaType,
    TopicCategory,
    Emotion,
    Action,
    create_slot,
    get_slots_summary,
    filter_incomplete_slots,
)

# Scheduler
from .scheduler import (
    LayeredBatchScheduler,
    BatchItem,
    SchedulerState,
    create_scheduler,
)

__version__ = "1.0.0"

__all__ = [
    # Configuration
    "DistributionConfig",
    "DistributionDimension",
    "LanguageRatios",
    "PersonaRatios",
    "TopicRatios",
    "get_default_config",
    "get_balanced_config",
    "get_chat_heavy_config",
    # Slot System
    "Slot",
    "SlotType",
    "Language",
    "PersonaType",
    "TopicCategory",
    "Emotion",
    "Action",
    "create_slot",
    "get_slots_summary",
    "filter_incomplete_slots",
    # Scheduler
    "LayeredBatchScheduler",
    "BatchItem",
    "SchedulerState",
    "create_scheduler",
]
