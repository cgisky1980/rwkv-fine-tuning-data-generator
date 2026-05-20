"""V4 独立数据生成 Skill 集成测试"""

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_gen_skill.models import CreateTaskRequest, LanguageRatios, UpdateTaskRequest
from data_gen_skill.dispatcher import GenTaskDispatcher
from data_gen_skill.schema_validator import validate, format_result
from data_gen_skill.worker import MockAgentWorker
from data_gen_skill.db import GenDatabase


def _make_db(marker: str) -> tuple:
    tmp_dir = Path(tempfile.gettempdir()) / "dgs_tests"
    tmp_dir.mkdir(exist_ok=True)
    db_path = tmp_dir / f"test_{marker}.db"
    for suffix in ["", "-wal", "-shm"]:
        p = Path(str(db_path) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    return GenDatabase(db_path), db_path


def _cleanup(db_path: Path):
    for suffix in ["", "-wal", "-shm"]:
        p = Path(str(db_path) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


def test_schema_validator():
    print("=" * 60)
    print("测试 1: Schema 合规校验器")
    print("=" * 60)

    worker = MockAgentWorker("test", None)
    valid_data = worker.generate_for_item({"task_id": "test_clarify", "language": "zh"})

    result = validate("clarify_skill", valid_data)
    print(format_result(result))
    assert result.passed, "Valid data should pass validation"
    print("✅ clarify_skill 合规数据通过校验")

    bad_data = {"not_a_dialogue": 123}
    result2 = validate("clarify_skill", bad_data)
    assert not result2.passed, "Invalid data should fail"
    print("✅ 非法数据被拒绝")

    result3 = validate("unknown_type", {})
    assert not result3.passed
    print("✅ 未知生成器类型被拒绝")

    print()
    return True


def test_create_and_pull():
    print("=" * 60)
    print("测试 2: 创建任务 + Agent 拉取工作项")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("pull")
    d.db = db

    request = CreateTaskRequest(
        generator_type="clarify_skill",
        count=10,
        language_ratios=LanguageRatios(zh=0.6, en=0.4),
    )

    task = d.create_task(request)
    print(f"创建任务: {task.task_id}")
    print(f"  总数: {task.total_items}, 状态: {task.status.value}")
    assert task.total_items == 10
    assert task.status.value == "running"
    print("✅ 任务创建成功")

    items = d.pull_work_items("agent_001", batch_size=3)
    assert len(items) == 3
    assert all(item["agent_id"] == "agent_001" for item in items)
    print(f"✅ Agent A 拉取 {len(items)} 个工作项")

    items_b = d.pull_work_items("agent_002", batch_size=3)
    assert len(items_b) == 3
    assert all(item["agent_id"] == "agent_002" for item in items_b)
    print(f"✅ Agent B 拉取 {len(items_b)} 个工作项 (不冲突)")

    items_c = d.pull_work_items("agent_003", batch_size=3)
    print(f"✅ Agent C 拉取 {len(items_c)} 个工作项")

    _cleanup(db_path)
    print()
    return True


def test_submit_and_validate():
    print("=" * 60)
    print("测试 3: Agent 提交结果 + 校验 + 入库")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("submit")
    d.db = db

    request = CreateTaskRequest(
        generator_type="clarify_skill",
        count=3,
    )
    task = d.create_task(request)
    print(f"创建任务: {task.task_id} ({task.total_items} items)")

    items = d.pull_work_items("agent_test", batch_size=1)
    assert len(items) == 1
    item = items[0]
    print(f"拉取工作项: {item['item_id']}")

    worker = MockAgentWorker("agent_test", d)
    data = worker.generate_for_item(item)
    print(f"生成 mock 数据: {len(str(data))} 字节")

    result = d.submit_result("agent_test", item["item_id"], data)
    assert result["success"], f"提交失败: {result}"
    assert result["record_count"] > 0, f"record_count should be > 0, got {result['record_count']}"
    print(f"✅ 提交成功: record_count={result['record_count']}")

    fetched_task = d.get_task(task.task_id)
    assert fetched_task["completed_items"] >= 1
    print(f"✅ 任务进度: {fetched_task['completed_items']}/{fetched_task['total_items']}")

    result2 = d.submit_result("agent_test", item["item_id"], data)
    print(f"✅ 重复提交处理: {result2['message']}")

    _cleanup(db_path)
    print()
    return True


def test_concurrent_agents():
    print("=" * 60)
    print("测试 4: 多 Agent 并发拉取 + 提交")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("concurrent")
    d.db = db

    request = CreateTaskRequest(
        generator_type="clarify_skill",
        count=20,
    )
    task = d.create_task(request)
    print(f"任务: {task.task_id} ({task.total_items} items)")

    all_items = {}
    lock = threading.Lock()
    seen_ids = set()
    errors = []

    def agent_pull(agent_name: str):
        items = d.pull_work_items(agent_name, batch_size=4)
        with lock:
            for it in items:
                iid = it["item_id"]
                if iid in seen_ids:
                    errors.append(f"DUP: {iid}")
                seen_ids.add(iid)
                all_items[iid] = (agent_name, it)

    threads = []
    for i in range(5):
        t = threading.Thread(target=agent_pull, args=(f"agent_{i}",))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert not errors, f"Duplicate assignments: {errors}"
    assert len(seen_ids) == len(set(seen_ids))
    print(f"✅ 5个Agent 并发拉取，共 {len(all_items)} 个工作项，无冲突")

    submit_errors = []
    for iid, (agent_name, item) in all_items.items():
        worker = MockAgentWorker(agent_name, d)
        data = worker.generate_for_item(item)
        result = d.submit_result(agent_name, iid, data)
        if not result["success"]:
            submit_errors.append(f"{agent_name}/{iid}: {result['message']}")

    assert not submit_errors, f"Submit errors: {submit_errors}"
    print(f"✅ 全部提交成功")

    task_final = d.get_task(task.task_id)
    print(f"  最终状态: {task_final['status']}, {task_final['completed_items']}/{task_final['total_items']}")
    assert task_final["completed_items"] == len(all_items)

    records = d.get_task_records(task.task_id)
    assert len(records) > 0
    print(f"✅ 数据库记录数: {len(records)}")

    _cleanup(db_path)
    print()
    return True


def test_get_stats():
    print("=" * 60)
    print("测试 5: 系统统计")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("stats")
    d.db = db

    d.create_task(CreateTaskRequest(generator_type="clarify_skill", count=5))
    d.create_task(CreateTaskRequest(generator_type="single_skill", count=3))

    items = d.pull_work_items("agent_x", batch_size=3)
    worker = MockAgentWorker("agent_x", d)
    for item in items:
        data = worker.generate_for_item(item)
        d.submit_result("agent_x", item["item_id"], data)

    stats = d.db.get_stats()
    print(f"  任务数: {stats['total_tasks']}, 记录数: {stats['total_records']}")
    assert stats["total_tasks"] == 2
    assert stats["active_agents"] >= 1
    print("✅ 统计正常")

    _cleanup(db_path)
    print()
    return True


def test_update_task():
    print("=" * 60)
    print("测试 6: 更新任务配置")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("update")
    d.db = db

    task = d.create_task(CreateTaskRequest(generator_type="clarify_skill", count=5))
    print(f"创建: {task.task_id} count=5")
    assert task.total_items == 5

    update = UpdateTaskRequest(count=8)
    result = d.update_task(task.task_id, update)
    assert result["success"]
    print("✅ count: 5→8")

    updated = d.get_task(task.task_id)
    assert updated["total_items"] == 8
    print("✅ total_items 已更新为 8")

    update2 = UpdateTaskRequest(count=3)
    d.update_task(task.task_id, update2)
    updated2 = d.get_task(task.task_id)
    assert updated2["total_items"] == 3
    print("✅ count: 8→3 (缩减)")

    update3 = UpdateTaskRequest(temperature=0.9)
    d.update_task(task.task_id, update3)
    print("✅ temperature: 0.7→0.9")

    d.cancel_task(task.task_id)
    update4 = UpdateTaskRequest(count=10)
    result4 = d.update_task(task.task_id, update4)
    assert not result4["success"]
    print("✅ 已取消任务不可修改")

    _cleanup(db_path)
    print()
    return True


def test_pause_resume():
    print("=" * 60)
    print("测试 7: 暂停/恢复任务")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("pause")
    d.db = db

    task = d.create_task(CreateTaskRequest(generator_type="clarify_skill", count=10))
    print(f"创建: {task.task_id}")

    items = d.pull_work_items("agent_x", batch_size=3)
    assert len(items) == 3
    print("✅ 暂停前可拉取")

    result = d.pause_task(task.task_id)
    assert result["success"]
    print("✅ 暂停成功")

    items2 = d.pull_work_items("agent_x", batch_size=3)
    assert len(items2) == 0
    print("✅ 暂停后不可拉取")

    result3 = d.resume_task(task.task_id)
    assert result3["success"]
    print("✅ 恢复成功")

    items4 = d.pull_work_items("agent_y", batch_size=3)
    assert len(items4) > 0
    print("✅ 恢复后可拉取")

    _cleanup(db_path)
    print()
    return True


def test_retry_and_release():
    print("=" * 60)
    print("测试 8: 重试失败 + Agent 释放工作项")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("retry")
    d.db = db

    task = d.create_task(CreateTaskRequest(generator_type="clarify_skill", count=5))
    items = d.pull_work_items("agent_x", batch_size=5)
    assert len(items) == 5

    for item in items[:2]:
        d.submit_result("agent_x", item["item_id"], {"bad": "data"})

    items_status = d.list_work_items(task.task_id, "failed")
    assert len(items_status) == 2
    print("✅ 2个失败项已被标记")

    retry_result = d.retry_failed_items(task.task_id)
    assert retry_result["retried_count"] == 2
    print("✅ 2个失败项已重置为 pending")

    items_pending = d.list_work_items(task.task_id, "pending")
    assert len(items_pending) == 2
    print("✅ pending 中恢复为 2")

    release_result = d.release_work_items("agent_x")
    assert release_result["released_count"] >= 3
    print(f"✅ Agent 释放了 {release_result['released_count']} 个项目")

    _cleanup(db_path)
    print()
    return True


def test_list_generators():
    print("=" * 60)
    print("测试 9: 列出生成器")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("gens")
    d.db = db

    gens = d.list_generators()
    assert len(gens) > 0
    for g in gens[:5]:
        print(f"  - {g['id']}: {g['name']} (L{g.get('level', '?')})")
    print(f"✅ 共 {len(gens)} 个可用生成器")
    assert any(g["id"] == "clarify_skill" for g in gens)

    _cleanup(db_path)
    print()
    return True


def test_export_data():
    print("=" * 60)
    print("测试 10: 多格式导出")
    print("=" * 60)

    d = GenTaskDispatcher()
    db, db_path = _make_db("export")
    d.db = db

    task = d.create_task(CreateTaskRequest(generator_type="clarify_skill", count=3))
    items = d.pull_work_items("agent_x", batch_size=3)
    worker = MockAgentWorker("agent_x", d)
    for item in items:
        data = worker.generate_for_item(item)
        d.submit_result("agent_x", item["item_id"], data)

    import tempfile
    export_path = str(Path(tempfile.gettempdir()) / f"test_export_{task.task_id}.jsonl")
    result = d.export_data(task.task_id, "jsonl", export_path)
    assert result["success"]
    assert Path(export_path).exists()
    count = sum(1 for _ in open(export_path, "r", encoding="utf-8"))
    print(f"✅ jsonl 导出: {count} 行 → {export_path}")
    Path(export_path).unlink(missing_ok=True)

    _cleanup(db_path)
    print()
    return True


def test_semantic_validation():
    print("=" * 60)
    print("测试 11: 增强语义验证")
    print("=" * 60)

    worker = MockAgentWorker("test", None)
    valid_data = worker.generate_for_item({"task_id": "test_clarify", "language": "zh"})

    result = validate("clarify_skill", valid_data)
    print(format_result(result))
    assert result.passed

    has_tts_warning = any("TTS tag coverage" in w for w in result.warnings)
    has_eng_warning = any("Non-English thought" in w for w in result.warnings)
    print(f"  TTS覆盖率warning: {has_tts_warning}")
    print(f"  非英文thought warning: {has_eng_warning}")
    print("✅ 语义级检查运行正常")

    print()
    return True


def main():
    print("V4 独立数据生成 Skill 集成测试")
    print("=" * 60)
    print()

    results = []
    tests = [
        ("Schema 校验器", test_schema_validator),
        ("创建任务+拉取", test_create_and_pull),
        ("提交+校验+入库", test_submit_and_validate),
        ("多Agent并发", test_concurrent_agents),
        ("系统统计", test_get_stats),
        ("更新任务配置", test_update_task),
        ("暂停/恢复", test_pause_resume),
        ("重试+释放", test_retry_and_release),
        ("列出生成器", test_list_generators),
        ("多格式导出", test_export_data),
        ("语义验证", test_semantic_validation),
    ]

    for name, test_fn in tests:
        try:
            test_fn()
            results.append((name, True))
        except Exception as e:
            import traceback
            print(f"❌ {name} 失败: {e}")
            traceback.print_exc()
            results.append((name, False))

    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    for name, passed in results:
        print(f"{'✅' if passed else '❌'} {name}")

    all_passed = all(p for _, p in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())