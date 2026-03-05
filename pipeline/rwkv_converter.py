"""V4 RWKV Data Format Converter

根据 RWKV 微调教程实现数据格式转换
教程: https://www.rwkv.cn/tutorials/advanced/Fine-Tune/FT-Dataset
"""

import json
import random
import re
from pathlib import Path
from typing import List, Dict, Any

from .common import extract_response_text


def convert_to_rwkv_single_turn(user_text: str, assistant_text: str) -> Dict[str, str]:
    """Convert to RWKV single-turn Q&A format

    Format: {"text": "User: 问题\n\nAssistant: 答案"}
    """
    # Remove TTS instruction from assistant text for RWKV training
    clean_assistant = extract_response_text(assistant_text)

    text = f"User: {user_text}\n\nAssistant: {clean_assistant}"
    text = _fix_trailing_newline(text)

    return {"text": text}


def convert_to_rwkv_multi_turn(turns: List[Dict[str, str]]) -> Dict[str, str]:
    """Convert to RWKV multi-turn conversation format

    Format: {"text": "User: 问题一\n\nAssistant: 答案一\n\nUser: 问题二\n\nAssistant: 答案二"}
    """
    parts = []
    for turn in turns:
        role = turn.get("role", "")
        content = turn.get("say", "") or turn.get("respond", "")

        if role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            # Remove TTS instruction
            clean_content = extract_response_text(content)
            parts.append(f"Assistant: {clean_content}")

    text = "\n\n".join(parts)
    text = _fix_trailing_newline(text)

    return {"text": text}


def convert_to_rwkv_instruction(
    instruction: str, input_text: str, response_text: str
) -> Dict[str, str]:
    """Convert to RWKV instruction format

    Format: {"text": "Instruction: 指令\n\nInput: 内容\n\nResponse: 答案"}
    """
    # Remove TTS instruction
    clean_response = extract_response_text(response_text)

    text = f"Instruction: {instruction}\n\nInput: {input_text}\n\nResponse: {clean_response}"
    text = _fix_trailing_newline(text)

    return {"text": text}


def _fix_trailing_newline(text: str) -> str:
    """Fix trailing newlines: replace \n or \n\n at the end with \n\n# User\n

    This ensures proper formatting for RWKV training where each
    conversation segment ends with a prompt for the next user input.
    """
    target = "\n\n# User\n\n"
    
    # If already has complete marker, return as is
    if text.endswith(target):
        return text
    
    # Check if ends with # User (with optional trailing newlines)
    # and replace appropriately
    if text.endswith('\n\n# User\n'):
        return text + '\n'
    elif text.endswith('\n\n# User'):
        return text + '\n\n'
    elif text.endswith('# User'):
        return text + '\n\n# User\n\n'
    elif text.endswith('\n# User'):
        return text + '# User\n\n'
    elif text.endswith('# Use') or text.endswith('# U'):
        idx = text.rfind('#')
        if idx > 0:
            base = text[:idx]
            if base.endswith('\n'):
                base = base[:-1]
            return base + target
        return text + target
    # No # User at all - handle trailing newlines
    elif text.endswith('\n\n'):
        return text + '# User\n\n'
    elif text.endswith('\n'):
        return text[:-1] + target
    else:
        return text + target


def convert_v4_record_to_rwkv(
    record: Dict[str, Any], format_type: str = "multi_turn"
) -> Dict[str, str]:
    """Convert V4 record to RWKV format

    Args:
        record: V4 data record
        format_type: "single_turn", "multi_turn", or "instruction"

    Returns:
        RWKV formatted record
    """
    turns = record.get("turns", [])

    if format_type == "single_turn" and len(turns) >= 2:
        # Extract first user-assistant pair
        user_turn = next((t for t in turns if t.get("role") == "user"), None)
        assistant_turn = next((t for t in turns if t.get("role") == "assistant"), None)

        if user_turn and assistant_turn:
            return convert_to_rwkv_single_turn(
                user_turn.get("say", ""), assistant_turn.get("respond", "")
            )

    elif format_type == "instruction":
        # For tool-based records, treat as instruction format
        user = record.get("user", {})
        assistant = record.get("assistant", {})

        if user and assistant:
            return convert_to_rwkv_instruction(
                instruction=user.get("say", ""),
                input_text=json.dumps(user.get("tools_usage", []), ensure_ascii=False),
                response_text=assistant.get("respond", ""),
            )

    # Default: multi-turn format
    if turns:
        return convert_to_rwkv_multi_turn(turns)

    return {"text": ""}


def shuffle_jsonl_data(
    input_file: Path, output_file: Path, repeat_times: int = 1, seed: int = 42
) -> int:
    """Shuffle JSONL data

    Equivalent to:
    awk 'NF > 0 {print}' data.jsonl data.jsonl data.jsonl | head -c -1 > repeated-data.jsonl
    sort -R repeated-data.jsonl | head -c -1 > shuffled-data.jsonl

    Args:
        input_file: Input JSONL file path
        output_file: Output JSONL file path
        repeat_times: Number of times to repeat the data
        seed: Random seed for reproducibility

    Returns:
        Number of lines written
    """
    random.seed(seed)

    # Read all lines
    lines = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:  # NF > 0 equivalent - skip empty lines
                lines.append(line)

    # Repeat data
    repeated_lines = lines * repeat_times

    # Shuffle
    random.shuffle(repeated_lines)

    # Write output (head -c -1 equivalent - remove last newline)
    with open(output_file, "w", encoding="utf-8") as f:
        for i, line in enumerate(repeated_lines):
            if i > 0:
                f.write("\n")
            f.write(line)

    return len(repeated_lines)


def merge_jsonl_files(
    input_files: List[Path], output_file: Path, shuffle: bool = True, seed: int = 42
) -> int:
    """Merge multiple JSONL files and optionally shuffle

    Args:
        input_files: List of input JSONL file paths
        output_file: Output JSONL file path
        shuffle: Whether to shuffle the merged data
        seed: Random seed

    Returns:
        Number of lines written
    """
    all_lines = []

    for input_file in input_files:
        with open(input_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_lines.append(line)

    if shuffle:
        random.seed(seed)
        random.shuffle(all_lines)

    # Write output
    with open(output_file, "w", encoding="utf-8") as f:
        for i, line in enumerate(all_lines):
            if i > 0:
                f.write("\n")
            f.write(line)

    return len(all_lines)


def add_regular_data(
    special_data_file: Path,
    regular_data_file: Path,
    output_file: Path,
    regular_ratio: float = 0.2,
    seed: int = 42,
) -> int:
    """Add regular data to special dataset to prevent overfitting

    As recommended in RWKV tutorial:
    - Add some regular conversation data to improve generalization
    - Recommended ratio: 20% regular data

    Args:
        special_data_file: Special task data (e.g., math problems)
        regular_data_file: Regular conversation data
        output_file: Output file path
        regular_ratio: Ratio of regular data (0.0 - 1.0)
        seed: Random seed

    Returns:
        Number of lines written
    """
    random.seed(seed)

    # Read special data
    special_lines = []
    with open(special_data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                special_lines.append(line)

    # Read regular data
    regular_lines = []
    with open(regular_data_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                regular_lines.append(line)

    # Calculate how much regular data to add
    total_special = len(special_lines)
    target_regular = int(total_special * regular_ratio / (1 - regular_ratio))

    # Sample regular data (with replacement if not enough)
    if len(regular_lines) >= target_regular:
        selected_regular = random.sample(regular_lines, target_regular)
    else:
        # Repeat regular data if not enough
        selected_regular = regular_lines * (target_regular // len(regular_lines) + 1)
        selected_regular = selected_regular[:target_regular]

    # Merge and shuffle
    all_lines = special_lines + selected_regular
    random.shuffle(all_lines)

    # Write output
    with open(output_file, "w", encoding="utf-8") as f:
        for i, line in enumerate(all_lines):
            if i > 0:
                f.write("\n")
            f.write(line)

    return len(all_lines)


def convert_v4_to_rwkv_jsonl(
    input_file: Path,
    output_file: Path,
    format_type: str = "multi_turn",
    shuffle: bool = True,
    repeat_times: int = 1,
    seed: int = 42,
) -> int:
    """Convert V4 JSONL data to RWKV format

    Args:
        input_file: Input V4 JSONL file
        output_file: Output RWKV JSONL file
        format_type: "single_turn", "multi_turn", or "instruction"
        shuffle: Whether to shuffle data
        repeat_times: Number of times to repeat data
        seed: Random seed

    Returns:
        Number of records converted
    """
    records = []

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                rwkv_record = convert_v4_record_to_rwkv(record, format_type)
                if rwkv_record.get("text"):
                    records.append(json.dumps(rwkv_record, ensure_ascii=False))
            except json.JSONDecodeError:
                continue

    # Repeat if needed
    all_records = records * repeat_times

    # Shuffle
    if shuffle:
        random.seed(seed)
        random.shuffle(all_records)

    # Write output
    with open(output_file, "w", encoding="utf-8") as f:
        for i, record in enumerate(all_records):
            if i > 0:
                f.write("\n")
            f.write(record)

    return len(all_records)


def estimate_binidx_size(jsonl_file: Path) -> Dict[str, Any]:
    """Estimate binidx file sizes

    Returns:
        Dict with file size estimates
    """
    jsonl_size = jsonl_file.stat().st_size

    # Rough estimates based on typical compression
    bin_size_estimate = jsonl_size * 0.4  # bin file is usually ~40% of JSONL
    idx_size_estimate = jsonl_size * 0.05  # idx file is ~5% of JSONL

    return {
        "jsonl_size_mb": round(jsonl_size / 1024 / 1024, 2),
        "estimated_bin_size_mb": round(bin_size_estimate / 1024 / 1024, 2),
        "estimated_idx_size_mb": round(idx_size_estimate / 1024 / 1024, 2),
        "total_estimated_mb": round(
            (jsonl_size + bin_size_estimate + idx_size_estimate) / 1024 / 1024, 2
        ),
    }
