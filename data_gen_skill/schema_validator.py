"""
Schema 合规校验器 — 验证 Agent 提交的数据是否符合生成器规范
"""

import re
from typing import Any, Dict, List, Tuple


class ValidationResult:
    def __init__(self):
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, msg: str):
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_clarify_skill(data: dict) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(data, dict):
        result.add_error("Data must be a dict")
        return result

    expected_cases = ["clarify_then_success", "clarify_then_error", "no_clarify_needed"]
    for case in expected_cases:
        if case not in data:
            result.add_error(f"Missing case: {case}")

    for case_name in expected_cases:
        case = data.get(case_name, {})
        if not isinstance(case, dict):
            result.add_error(f"{case_name} must be a dict")
            continue

        dialogue = case.get("dialogue", [])
        if not isinstance(dialogue, list) or len(dialogue) == 0:
            result.add_error(f"{case_name}.dialogue must be a non-empty list")
            continue

        _validate_dialogue(dialogue, f"{case_name}.dialogue", result, is_clarify=True)

    return result


def validate_single_skill(data: dict) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(data, dict):
        result.add_error("Data must be a dict")
        return result

    expected_cases = ["success_case", "error_case", "cancelled_case"]
    for case in expected_cases:
        if case not in data:
            result.add_warning(f"Missing case: {case}")

    for case_name in expected_cases:
        case = data.get(case_name, {})
        if not isinstance(case, dict):
            continue
        dialogue = case.get("dialogue", [])
        if isinstance(dialogue, list) and len(dialogue) > 0:
            _validate_dialogue(dialogue, f"{case_name}.dialogue", result, is_clarify=False)

    return result


def validate_single_skill_error(data: dict) -> ValidationResult:
    return validate_single_skill(data)


def validate_mixed_dialog(data: dict) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(data, dict):
        result.add_error("Data must be a dict")
        return result

    expected_cases = ["chat_first_case", "tool_first_case", "interleaved_case"]
    for case in expected_cases:
        if case not in data:
            result.add_warning(f"Missing case: {case}")

    for case_name in expected_cases:
        case = data.get(case_name, {})
        if not isinstance(case, dict):
            continue
        dialogue = case.get("dialogue", [])
        if isinstance(dialogue, list) and len(dialogue) > 0:
            _validate_dialogue(dialogue, f"{case_name}.dialogue", result, is_clarify=False)

    return result


def validate_complex_skill(data: dict) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(data, dict):
        result.add_error("Data must be a dict")
        return result

    expected_cases = ["multi_step_case", "orchestration_case", "parallel_case"]
    for case in expected_cases:
        if case not in data:
            result.add_warning(f"Missing case: {case}")

    for case_name in expected_cases:
        case = data.get(case_name, {})
        if not isinstance(case, dict):
            continue
        dialogue = case.get("dialogue", [])
        if isinstance(dialogue, list) and len(dialogue) > 0:
            _validate_dialogue(dialogue, f"{case_name}.dialogue", result, is_clarify=False)

    return result


def validate_no_tool(data: dict) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(data, dict):
        result.add_error("Data must be a dict")
        return result

    dialogue = data.get("dialogue", [])
    if not isinstance(dialogue, list) or len(dialogue) == 0:
        result.add_error("dialogue must be a non-empty list")
        return result

    _validate_dialogue(dialogue, "dialogue", result, is_clarify=False)
    return result


VALIDATORS = {
    "clarify_skill": validate_clarify_skill,
    "single_skill": validate_single_skill,
    "single_skill_error": validate_single_skill_error,
    "mixed_dialog": validate_mixed_dialog,
    "complex_skill": validate_complex_skill,
    "no_tool": validate_no_tool,
}


def validate(generator_type: str, data: dict) -> ValidationResult:
    validator = VALIDATORS.get(generator_type)
    if validator is None:
        result = ValidationResult()
        result.add_error(f"Unknown generator type: {generator_type}")
        return result
    return validator(data)


def _validate_dialogue(
    dialogue: list, path: str, result: ValidationResult, is_clarify: bool
):
    seen_roles = set()
    has_clarify = False
    has_skill_call = False

    for i, turn in enumerate(dialogue):
        prefix = f"{path}[{i}]"
        if not isinstance(turn, dict):
            result.add_error(f"{prefix}: must be a dict")
            continue

        role = turn.get("role", "")
        if role not in ("user", "assistant"):
            result.add_error(f"{prefix}: invalid role '{role}'")
            continue

        seen_roles.add(role)

        if role == "user":
            if "say" not in turn or not isinstance(turn["say"], str):
                result.add_error(f"{prefix}: user must have 'say' string")
            turn_type = turn.get("type", "")
            if turn_type == "clarify_needed":
                has_clarify = True

        elif role == "assistant":
            _validate_assistant_turn(turn, prefix, result, is_clarify)

            if "skill_calls" in turn:
                has_skill_call = True
                skill_calls = turn["skill_calls"]
                for si, sc in enumerate(skill_calls):
                    _validate_skill_call(sc, f"{prefix}.skill_calls[{si}]", result)

            thought = turn.get("thought", [])
            if isinstance(thought, list) and thought:
                action = thought[0].get("action", "") if isinstance(thought[0], dict) else ""
                if action == "clarify":
                    has_clarify = True

    if is_clarify:
        if path.endswith("clarify_then_success") or path.endswith("clarify_then_error"):
            if not has_clarify:
                result.add_warning(f"{path}: expected clarify action but none found")
        if path.endswith("no_clarify_needed"):
            if has_clarify:
                result.add_warning(f"{path}: expected no clarify but found clarify")


def _validate_assistant_turn(
    turn: dict, prefix: str, result: ValidationResult, is_clarify: bool
):
    respond = turn.get("respond", "")
    if not respond or not isinstance(respond, str):
        result.add_error(f"{prefix}: assistant must have 'respond' string")
    else:
        # 检查 TTS 标签
        if "{V:" not in respond:
            result.add_warning(f"{prefix}: respond missing TTS tag {{V:...}}")

    thought = turn.get("thought", [])
    if isinstance(thought, list) and thought:
        for ti, t in enumerate(thought):
            if not isinstance(t, dict):
                continue
            for key in ["observation", "reasoning"]:
                val = t.get(key, "")
                if val and isinstance(val, str):
                    # Check if thought is in English (basic check)
                    if not _is_likely_english(val):
                        result.add_warning(
                            f"{prefix}.thought[{ti}].{key}: should be in English"
                        )

            action = t.get("action", "")
            if is_clarify and action:
                pass


def _validate_skill_call(sc: dict, prefix: str, result: ValidationResult):
    if not isinstance(sc, dict):
        result.add_error(f"{prefix}: must be a dict")
        return

    if "skill_call" not in sc:
        result.add_error(f"{prefix}: missing 'skill_call'")
    else:
        call = sc["skill_call"]
        if isinstance(call, dict):
            if "name" not in call:
                result.add_error(f"{prefix}.skill_call: missing 'name'")

    if "skill_respond" not in sc:
        result.add_warning(f"{prefix}: missing 'skill_respond'")

    if "skill_output" not in sc:
        result.add_warning(f"{prefix}: missing 'skill_output'")
    else:
        output = sc["skill_output"]
        if isinstance(output, dict):
            status = output.get("status", "")
            if status not in ("success", "error", "cancelled"):
                result.add_warning(
                    f"{prefix}.skill_output.status: unexpected '{status}'"
                )


def _is_likely_english(text: str) -> bool:
    if not text:
        return True
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff")
    return cjk_count == 0


def format_result(result: ValidationResult) -> str:
    lines = [f"Validation {'PASSED' if result.passed else 'FAILED'}"]
    for e in result.errors:
        lines.append(f"  ❌ {e}")
    for w in result.warnings:
        lines.append(f"  ⚠️  {w}")
    return "\n".join(lines)