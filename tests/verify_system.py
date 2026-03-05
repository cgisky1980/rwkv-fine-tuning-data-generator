"""验证 V4 系统完整性"""

import sys
from pathlib import Path


def check_structure():
    """检查项目结构"""
    v4_path = Path(__file__).parent.parent

    checks = [
        (
            "Pipeline modules",
            [
                "pipeline/common.py",
                "pipeline/generate_base.py",
                "pipeline/generate_no_tool.py",
                "pipeline/generate_tool.py",
                "pipeline/rwkv_converter.py",
                "pipeline/binidx_converter.py",
            ],
        ),
        (
            "Integrated RWKV tool",
            [
                "pipeline/json2binidx_tool/tools/preprocess_data.py",
                "pipeline/json2binidx_tool/rwkv_vocab_v20230424.txt",
            ],
        ),
        (
            "Web interface",
            [
                "web/backend/main.py",
                "web/frontend/index.html",
            ],
        ),
        (
            "Config & tests",
            [
                "data/persona_config.json",
                "tests/test_generator.py",
            ],
        ),
    ]

    print("=" * 60)
    print("V4 Data Generator - System Check")
    print("=" * 60)

    all_ok = True
    for category, files in checks:
        print(f"\n[ {category} ]")
        for file in files:
            path = v4_path / file
            status = "OK" if path.exists() else "MISSING"
            print(f"  [{status}] {file}")
            if not path.exists():
                all_ok = False

    print("\n" + "=" * 60)
    if all_ok:
        print("SUCCESS: All components are present!")
        print("\nQuick start:")
        print("  1. pip install -r requirements.txt")
        print("  2. python web/backend/main.py")
        print("  3. Open http://localhost:8000")
    else:
        print("ERROR: Some components are missing!")
        return 1

    print("=" * 60)
    return 0


def test_imports():
    """测试关键导入"""
    print("\nTesting imports...")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from pipeline.common import LLMClient

        print("  [OK] LLMClient imported")

        from pipeline.generate_no_tool import NoToolGenerator

        print("  [OK] NoToolGenerator imported")

        from pipeline.generate_tool import ToolGenerator

        print("  [OK] ToolGenerator imported")

        from pipeline.rwkv_converter import convert_v4_record_to_rwkv

        print("  [OK] rwkv_converter imported")

        from pipeline.binidx_converter import BinidxConverter

        print("  [OK] binidx_converter imported")

        # Test integrated tool
        converter = BinidxConverter()
        if converter.is_installed():
            print("  [OK] Integrated json2binidx_tool detected")
        else:
            print("  [WARN] json2binidx_tool not found (will be checked at runtime)")

        return 0
    except Exception as e:
        print(f"  [ERROR] Import error: {e}")
        return 1


if __name__ == "__main__":
    result1 = check_structure()
    result2 = test_imports()

    sys.exit(result1 or result2)
