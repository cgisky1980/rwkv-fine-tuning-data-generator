"""V4 有技能生成器测试脚本 - 验证 BaseSkillGenerator 和 L1Generator"""

import asyncio
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add V4 to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.generate_base import BaseSkillGenerator
from pipeline.generate_l1 import L1Generator


async def test_l1_generator():
    """测试 L1 生成器（单技能）"""
    print("=" * 80)
    print("测试 V4 L1 单技能生成器")
    print("=" * 80)
    print()

    # 加载 .env 文件
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    
    api_key = os.getenv("DEEPSEEK_API_KEY", "sk-test")
    generator = L1Generator(api_key=api_key)

    try:
        skills = [
            {
                "name": "weather_api",
                "alias": "天象探查术",
                "description": "获取指定位置的天气信息"
            },
            {
                "name": "list_directory",
                "alias": "目录探查",
                "description": "列出指定目录下的所有文件和子目录"
            },
            {
                "name": "read_file",
                "alias": "圣典阅览",
                "description": "读取指定路径的文件内容"
            }
        ]
        result, error_type, error_msg = await generator.generate_one(
            idx=0,
            skills=skills,
            persona={
                "name": "小助",
                "gender": {"name": "女", "description": "温柔可爱的女孩"},
                "identity": {"name": "助理", "description": "你的专属智能助手"},
                "personality": {"name": "温柔", "description": "语气柔和，关心用户"},
                "tone": {"name": "温柔语气", "description": "温柔、耐心"},
                "optional_tics": ["嗯", "啊", "那个"],
                "user_title": {"name": "您", "description": "对用户的尊称"},
                "language": "zh",
                "role": "assistant",
            },
            user_profile_ref=None,
            temperature=0.7,
            seed=42,
            max_tokens=3000,
        )

        if error_type:
            print(f"❌ 错误: {error_type} - {error_msg}")
            return False

        print("✅ 生成成功！")
        print()

        # 保存结果到文件
        output_path = Path(__file__).parent.parent / "tests" / "test_result.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"📝 结果已保存到: {output_path}")
        print()

        if isinstance(result, list):
            print(f"生成了 {len(result)} 个样本:")
            for i, payload in enumerate(result):
                print(f"\n{'='*60}")
                print(f"样本 #{i+1} (ID: {payload.get('id')})")
                print(f"{'='*60}")
                print(f"级别: {payload.get('meta', {}).get('level')}")
                print(f"结果类型: {payload.get('meta', {}).get('result_type')}")
                print(f"是否模拟错误: {payload.get('meta', {}).get('is_simulated_error', False)}")

                user = payload.get("user", {})
                print(f"\n用户输入: {user.get('say', '')[:100]}...")
                print(f"技能列表: {[t.get('name') for t in user.get('skills_usage', [])]}")
                print(f"引用信息数: {len(user.get('refs', []))}")

                assistant = payload.get("assistant", {})
                print(f"\n思考链数: {len(assistant.get('thought', []))}")
                print(f"技能调用数: {len(assistant.get('skill_calls', []))}")
                respond = assistant.get('respond', '')
                if respond.startswith('{'):
                    print(f"回复 (TTS格式): {respond[:80]}...")
                else:
                    print(f"⚠️  回复 (非TTS格式): {respond[:80]}...")

                for j, sc in enumerate(assistant.get("skill_calls", [])):
                    print(f"\n  技能调用 #{j+1}:")
                    print(f"    步骤: {sc.get('step')}")
                    print(f"    有 skill_doc: {'skill_doc' in sc}")
                    if 'skill_doc' in sc:
                        print(f"    skill_doc 内容: {str(sc.get('skill_doc', ''))[:100]}...")
                    print(f"    技能: {sc.get('skill_call', {}).get('name')}")
                    print(f"    有输出: {'skill_output' in sc}")
                    if 'skill_output' in sc:
                        print(f"    输出状态: {sc.get('skill_output', {}).get('status')}")
        else:
            print("返回结果非列表类型")
            print(json.dumps(result, ensure_ascii=False, indent=2)[:500])

        print()
        return True

    except Exception as e:
        import traceback
        print(f"❌ 异常: {e}")
        traceback.print_exc()
        return False
    finally:
        await generator.close()


async def test_base_skill_generator_abstract():
    """验证 BaseSkillGenerator 正确地是一个抽象基类"""
    print("=" * 80)
    print("验证 BaseSkillGenerator 抽象基类")
    print("=" * 80)
    print()

    try:
        # 尝试直接实例化抽象基类应该会失败
        generator = BaseSkillGenerator(api_key="sk-test")
        print("❌ 错误: 应该无法直接实例化 BaseSkillGenerator 抽象基类")
        return False
    except TypeError as e:
        print(f"✅ 正确: 抽象基类无法直接实例化 - {type(e).__name__}")
        return True


async def main():
    """运行所有测试"""
    print("V4 有技能生成器测试套件")
    print("=" * 80)
    print()

    results = []

    try:
        results.append(("BaseSkillGenerator 抽象基类", await test_base_skill_generator_abstract()))
    except Exception as e:
        print(f"❌ BaseSkillGenerator 抽象基类测试失败: {e}")
        results.append(("BaseSkillGenerator 抽象基类", False))

    try:
        results.append(("L1 单技能生成器", await test_l1_generator()))
    except Exception as e:
        print(f"❌ L1 单技能生成器测试失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("L1 单技能生成器", False))

    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    for name, passed in results:
        status = "✅ 测试通过" if passed else "❌ 测试失败"
        print(f"{status}: {name}")

    all_passed = all(passed for _, passed in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
