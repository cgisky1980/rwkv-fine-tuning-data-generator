"""V4 独立数据生成 Skill 集成测试"""

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_gen_skill.models import CreateTaskRequest, LanguageRatios
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