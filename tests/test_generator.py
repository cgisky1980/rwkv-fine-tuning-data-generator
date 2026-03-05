"""V4 Data Generator Test Script"""

import asyncio
import json
import sys
from pathlib import Path

# Add V4 to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.generate_no_tool import NoToolGenerator
from pipeline.generate_tool import ToolGenerator


async def test_no_tool_generator():
    """Test no-tool conversation generator"""
    print("=" * 60)
    print("Testing V4 No-Tool Generator")
    print("=" * 60)

    generator = NoToolGenerator(api_key="sk-test")

    result, error_type, error_msg = await generator.generate_one(
        idx=0, temperature=0.7, seed=42, user_profile_ratio=0.0, max_tokens=2000
    )

    if error_type:
        print(f"❌ Error: {error_type} - {error_msg}")
        return False

    print(f"✅ Generated conversation ID: {result.get('id')}")
    print(f"   Level: {result.get('level')}")
    print(f"   Topic: {result.get('topic', {}).get('topic')}")

    turns = result.get("turns", [])
    print(f"   Turns: {len(turns)}")

    for i, turn in enumerate(turns[:4]):  # Show first 4 turns
        role = turn.get("role")
        if role == "user":
            print(f"   [{i}] User: {turn.get('say', '')[:50]}...")
        else:
            respond = turn.get("respond", "")
            # Check TTS format
            if respond.startswith("("):
                print(f"   [{i}] Assistant: {respond[:80]}...")
            else:
                print(f"   ⚠️  [{i}] Assistant (no TTS format): {respond[:50]}...")

            # Verify no thought field
            if "thought" in turn:
                print(f"   ⚠️  WARNING: Found 'thought' field in no-tool response!")

    print()
    return True


async def test_tool_generator():
    """Test tool conversation generator"""
    print("=" * 60)
    print("Testing V4 Tool Generator")
    print("=" * 60)

    generator = ToolGenerator(api_key="sk-test")

    result, error_type, error_msg = await generator.generate_one(
        idx=0,
        tools_per_record=1,
        temperature=0.7,
        seed=42,
        user_profile_ratio=0.0,
        max_tokens=2000,
    )

    if error_type:
        print(f"❌ Error: {error_type} - {error_msg}")
        return False

    print(f"✅ Generated conversation ID: {result.get('id')}")
    print(f"   Level: {result.get('level')}")
    print(f"   Force Refusal: {result.get('meta', {}).get('force_refusal')}")

    assistant = result.get("assistant", {})
    print(f"   Has thought: {'thought' in assistant}")
    print(f"   Tool calls: {len(assistant.get('tool_calls', []))}")

    # Check TTS format in respond
    respond = assistant.get("respond", "")
    if respond.startswith("("):
        print(f"   Respond TTS format: ✅ {respond[:60]}...")
    else:
        print(f"   Respond TTS format: ❌ {respond[:50]}...")

    # Check tool_respond for each tool call
    for tc in assistant.get("tool_calls", []):
        tool_respond = tc.get("tool_respond", "")
        if tool_respond.startswith("("):
            print(f"   Tool respond TTS: ✅ {tool_respond[:60]}...")
        else:
            print(f"   Tool respond TTS: ❌ {tool_respond[:50]}...")

        # Check tool_risk
        tool_risk = tc.get("tool_risk")
        print(f"   Tool risk: {tool_risk}")

        # If tool_risk is false, should not have tool_output
        if tool_risk is False and "tool_output" in tc:
            print(f"   ⚠️  WARNING: tool_risk=false but tool_output exists!")
        elif tool_risk is True and "tool_output" not in tc:
            print(f"   ⚠️  WARNING: tool_risk=true but no tool_output!")

    print()
    return True


async def main():
    """Run all tests"""
    print("V4 Data Generator Test Suite")
    print("=" * 60)
    print()

    results = []

    try:
        results.append(("No-Tool Generator", await test_no_tool_generator()))
    except Exception as e:
        print(f"❌ No-Tool Generator failed: {e}")
        results.append(("No-Tool Generator", False))

    try:
        results.append(("Tool Generator", await test_tool_generator()))
    except Exception as e:
        print(f"❌ Tool Generator failed: {e}")
        results.append(("Tool Generator", False))

    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
