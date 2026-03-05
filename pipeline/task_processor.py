"""V4 Background Task Processor with Distribution Scheduler

Processes data generation tasks asynchronously with thread pool.
Uses LayeredBatchScheduler to control distribution across all dimensions.
Supports real-time progress updates and cancellation.
"""

import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
import queue

from .task_manager import (
    TaskManager,
    Task,
    TaskStatus,
    TaskStats,
    TaskConfig,
    get_task_manager,
)
from .distribution import (
    LayeredBatchScheduler,
    DistributionConfig,
    get_default_config,
    BatchItem,
)

class TaskProcessor:
    """Background task processor with thread pool and distribution control"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_manager = get_task_manager()

        # Progress callbacks: task_id -> list of callbacks
        self._progress_callbacks: Dict[str, List[Callable]] = {}
        self._callbacks_lock = threading.Lock()

        # Processing queue for pending tasks
        self._processing = False
        self._process_thread: Optional[threading.Thread] = None

        # Active schedulers: task_id -> scheduler
        self._schedulers: Dict[str, LayeredBatchScheduler] = {}
        self._schedulers_lock = threading.Lock()

    def start(self):
        """Start the background processor"""
        if not self._processing:
            self._processing = True
            self._process_thread = threading.Thread(
                target=self._process_queue, daemon=True
            )
            self._process_thread.start()
            print(f"Task processor started with {self.max_workers} workers")

    def stop(self):
        """Stop the background processor"""
        self._processing = False
        if self._process_thread:
            self._process_thread.join(timeout=5)
        self.executor.shutdown(wait=False)
        print("Task processor stopped")

    def _process_queue(self):
        """Process pending tasks from queue"""
        while self._processing:
            try:
                # Get pending tasks
                pending_tasks = self.task_manager.get_pending_tasks()

                # Get currently running task IDs
                running_task_ids = {t.id for t in self.task_manager.get_running_tasks()}

                for task in pending_tasks[: self.max_workers]:
                    if not self._processing:
                        break

                    # Skip if task is already running or completed
                    if task.id in running_task_ids:
                        continue

                    # Submit task to thread pool
                    self.executor.submit(self._execute_task, task)

                # Check running tasks count
                running_count = len(self.task_manager.get_running_tasks())
                available_slots = self.max_workers - running_count

                if available_slots <= 0 or not pending_tasks:
                    # Sleep if no work or slots full
                    time.sleep(1)

            except Exception as e:
                print(f"Error in process queue: {e}")
                time.sleep(1)

    def _get_or_create_scheduler(self, task: Task) -> LayeredBatchScheduler:
        """Get existing scheduler or create new one for task"""
        with self._schedulers_lock:
            if task.id in self._schedulers:
                return self._schedulers[task.id]

            # Create new scheduler from task config
            config = task.config.get_distribution_config()
            selected_topics = getattr(task.config, "selected_topics", None)
            scheduler = LayeredBatchScheduler(config, selected_topics=selected_topics)

            # Try to load saved state if exists
            state_path = task.get_scheduler_state_path()
            if state_path and state_path.exists():
                try:
                    scheduler.load_state(str(state_path))
                    print(f"Loaded scheduler state for task {task.id}")
                except Exception as e:
                    print(f"Failed to load scheduler state: {e}")

            self._schedulers[task.id] = scheduler
            return scheduler

    def _save_scheduler_state(self, task: Task, scheduler: LayeredBatchScheduler):
        """Save scheduler state for resumability"""
        state_dir = Path(task.data_file).parent / "scheduler_states"
        state_dir.mkdir(exist_ok=True)
        state_path = state_dir / f"{task.id}_scheduler.json"

        try:
            scheduler.save_state(str(state_path))
            # Update task record
            task.scheduler_state_file = str(state_path)
            self.task_manager.update_task_stats(task.id, task.stats)
        except Exception as e:
            print(f"Failed to save scheduler state: {e}")

    def _execute_task(self, task: Task):
        """Execute a single task with distribution control"""
        print(f"[TaskProcessor] _execute_task called for task {task.id}")
        task_id = task.id
        cancellation_event = threading.Event()

        # Register cancellation event
        self.task_manager.register_cancellation_event(task_id, cancellation_event)

        try:
            # Update status to running
            self.task_manager.update_task_status(task_id, TaskStatus.RUNNING)

            # Update stats
            stats = task.stats
            stats.start_time = datetime.now().isoformat()
            self.task_manager.update_task_stats(task_id, stats)

            # Get or create scheduler
            scheduler = self._get_or_create_scheduler(task)

            # Execute generation with distribution control
            self._generate_data_with_scheduler(task, scheduler, cancellation_event)

            # Check if cancelled
            if cancellation_event.is_set():
                self.task_manager.update_task_status(task_id, TaskStatus.CANCELLED)
                self._notify_progress(task_id, {"status": "cancelled"})
            else:
                # Mark as completed
                stats.end_time = datetime.now().isoformat()
                # Sync final stats from scheduler (in case of any discrepancy)
                stats.records_generated = scheduler.total_completed
                stats.records_failed = scheduler.total_failed
                self.task_manager.update_task_stats(task_id, stats)
                self.task_manager.update_task_status(task_id, TaskStatus.COMPLETED)
                self._notify_progress(
                    task_id, {"status": "completed", "stats": stats.to_dict()}
                )

        except Exception as e:
            error_msg = str(e)
            print(f"Task {task_id} failed: {error_msg}")
            self.task_manager.update_task_status(task_id, TaskStatus.FAILED, error_msg)
            self._notify_progress(task_id, {"status": "failed", "error": error_msg})

        finally:
            # Unregister cancellation event
            self.task_manager.unregister_cancellation_event(task_id)

            # Remove scheduler from active list
            with self._schedulers_lock:
                if task_id in self._schedulers:
                    del self._schedulers[task_id]

    def _generate_data_with_scheduler(
        self,
        task: Task,
        scheduler: LayeredBatchScheduler,
        cancellation_event: threading.Event,
    ):
        """Generate data using scheduler for distribution control"""
        config = task.config
        stats = task.stats
        batch_size = config.concurrency

        # Initialize generator with API key from provider config or environment
        provider_config = None
        api_key = None
        base_url = None
        model = None
        supports_json_object = True  # Default to True

        if config.provider_id:
            # Load provider configuration from llm_providers.json
            providers_file = (
                Path(__file__).parent.parent / "data" / "llm_providers.json"
            )
            print(f"[Task {task.id}] Looking for providers at: {providers_file}")
            print(f"[Task {task.id}] File exists: {providers_file.exists()}")
            if providers_file.exists():
                try:
                    with open(providers_file, "r", encoding="utf-8") as f:
                        providers_data = json.load(f)
                        providers = providers_data.get("providers", {})
                        print(
                            f"[Task {task.id}] Loaded providers: {list(providers.keys())}"
                        )
                        print(
                            f"[Task {task.id}] Looking for provider_id: {config.provider_id}"
                        )
                        if config.provider_id in providers:
                            provider_config = providers[config.provider_id]
                            api_key = provider_config.get("api_key")
                            base_url = provider_config.get("base_url")
                            model = provider_config.get("model", "gpt-4o")
                            supports_json_object = provider_config.get("supports_json_object", True)
                            print(
                                f"[Task {task.id}] Using provider: {provider_config.get('name', config.provider_id)}, model: {model}, supports_json_object: {supports_json_object}"
                            )
                        else:
                            print(
                                f"[Task {task.id}] Provider ID not found, using fallback"
                            )
                except Exception as e:
                    print(f"[Task {task.id}] Error loading provider config: {e}")

        # Fallback to environment or default
        if not api_key:
            api_key = os.getenv("DEEPSEEK_API_KEY", "sk-test")
        if not base_url:
            base_url = os.getenv("BASE_URL", "https://api.deepseek.com")
        if not model:
            model = os.getenv("MODEL", "deepseek-chat")

        provider_id = config.provider_id

        from .generator import UniversalGenerator
        generator = UniversalGenerator(
            generator_id=config.generator_type,
            api_key=api_key, 
            base_url=base_url, 
            model=model, 
            supports_json_object=supports_json_object, 
            provider_id=provider_id
        )

        try:
            # Open data file for writing
            with open(task.data_file, "a", encoding="utf-8") as f:
                start_time = time.time()
                last_update = start_time
                last_save = start_time

                # Worker pool mode: maintain fixed concurrency, start new task immediately when one completes
                # Real-time scheduler updates to maintain distribution balance
                semaphore = asyncio.Semaphore(batch_size)
                pending_tasks = {}
                task_id_counter = 0
                completed_count = 0
                failed_count = 0
                results_lock = asyncio.Lock()

                async def worker(item: BatchItem, task_id: int):
                    """Worker that generates one item and returns result"""
                    async with semaphore:
                        try:
                            result = await self._generate_for_slot_async(
                                generator, item, config.temperature, config.seed, config.user_profile_ratio
                            )
                            return (item, result, None)
                        except Exception as e:
                            return (item, None, str(e))

                async def process_result(item: BatchItem, result: Optional[Dict], error: Optional[str]):
                    """Process a completed result in real-time"""
                    nonlocal completed_count, failed_count, last_update, last_save
                    
                    if error:
                        print(f"Error generating for slot {item.slot_id}: {error}")
                        scheduler.record_result(item.slot_id, False)
                        async with results_lock:
                            failed_count += 1
                        stats.records_failed += 1
                    elif result:
                        f.write(json.dumps(result, ensure_ascii=False) + "\n")
                        f.flush()
                        scheduler.record_result(item.slot_id, True)
                        async with results_lock:
                            completed_count += 1
                        stats.records_generated += 1
                        
                        # Update stats in real-time
                        current_time = time.time()
                        elapsed = current_time - start_time
                        if elapsed > 0:
                            stats.current_speed = (stats.records_generated / elapsed) * 60
                        remaining = scheduler.total_remaining
                        if stats.current_speed > 0:
                            stats.estimated_remaining = int((remaining / stats.current_speed) * 60)
                        
                        # Notify progress
                        if current_time - last_update >= 1:
                            self.task_manager.update_task_stats(task.id, stats)
                            self._notify_progress(
                                task.id,
                                {
                                    "status": "running",
                                    "progress": stats.records_generated,
                                    "total": config.count,
                                    "stats": stats.to_dict(),
                                    "scheduler_status": scheduler.get_status(),
                                },
                            )
                            last_update = current_time
                        
                        # Save state periodically
                        if current_time - last_save >= 30:
                            self._save_scheduler_state(task, scheduler)
                            last_save = current_time
                    else:
                        scheduler.record_result(item.slot_id, False)
                        async with results_lock:
                            failed_count += 1
                        stats.records_failed += 1

                async def run_with_pool():
                    nonlocal task_id_counter
                    while not scheduler.is_complete and not cancellation_event.is_set():
                        # Fill up to batch_size pending tasks
                        while len(pending_tasks) < batch_size and not scheduler.is_complete:
                            # Check remaining before getting next batch
                            if scheduler.total_remaining <= 0:
                                break
                            batch = scheduler.next_batch(batch_size=1)
                            if not batch:
                                break
                            item = batch[0]
                            task_id = task_id_counter
                            task_id_counter += 1
                            slot_task = asyncio.create_task(worker(item, task_id))
                            pending_tasks[task_id] = (slot_task, item)
                        
                        if not pending_tasks:
                            break
                        
                        # Wait for any task to complete
                        done, _ = await asyncio.wait(
                            [t for t, _ in pending_tasks.values()],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Process completed tasks immediately (real-time scheduler update)
                        for completed_task in done:
                            for tid, (slot_task, item) in list(pending_tasks.items()):
                                if slot_task == completed_task:
                                    del pending_tasks[tid]
                                    try:
                                        item, result, error = completed_task.result()
                                        await process_result(item, result, error)
                                    except Exception as e:
                                        await process_result(item, None, str(e))
                                    break
                        
                        # Check if complete after processing
                        if scheduler.is_complete:
                            break
                    
                    # Wait for remaining tasks
                    if pending_tasks:
                        remaining_tasks = [t for t, _ in pending_tasks.values()]
                        done, _ = await asyncio.wait(remaining_tasks)
                        for completed_task in done:
                            for tid, (slot_task, item) in list(pending_tasks.items()):
                                if slot_task == completed_task:
                                    del pending_tasks[tid]
                                    try:
                                        item, result, error = completed_task.result()
                                        await process_result(item, result, error)
                                    except Exception as e:
                                        await process_result(item, None, str(e))
                                    break

                try:
                    loop = asyncio.get_running_loop()
                    loop.run_until_complete(run_with_pool())
                except RuntimeError:
                    asyncio.run(run_with_pool())

                # Final stats update
                self.task_manager.update_task_stats(task.id, stats)

                # Final scheduler save
                self._save_scheduler_state(task, scheduler)

        finally:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(generator.close())
            except RuntimeError:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, generator.close())
                    future.result()

    async def _generate_for_slot_async(
        self,
        generator,
        item: BatchItem,
        temperature: float,
        seed: Optional[int],
        user_profile_ratio: float,
    ) -> Optional[Dict]:
        """Generate a single record for a slot (async version)"""
        language = item.language
        topic = item.topic  # Use slot's topic

        try:
            result, error_type, error_msg = await generator.generate_one(
                idx=0,
                temperature=temperature,
                seed=seed,
                user_profile_ratio=user_profile_ratio,
                max_tokens=8192,
                language=language,
                topics=[topic] if topic else None,  # Pass topic constraint
            )

            if error_type:
                print(f"[ERROR] Generation failed: {error_type} - {error_msg}")
                return None
            return result

        except Exception as e:
            print(f"Generation error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _generate_for_slot(
        self,
        generator,
        item: BatchItem,
        temperature: float,
        seed: Optional[int],
        user_profile_ratio: float,
    ) -> Optional[Dict]:
        """Generate a single record for a slot"""
        language = item.language
        topic = item.topic  # Use slot's topic

        try:
            async def run_generation():
                return await generator.generate_one(
                    idx=0,
                    temperature=temperature,
                    seed=seed,
                    user_profile_ratio=user_profile_ratio,
                    max_tokens=8192,
                    language=language,
                    topics=[topic] if topic else None,  # Pass topic constraint
                )

            try:
                loop = asyncio.get_running_loop()
                result, error_type, error_msg = loop.run_until_complete(run_generation())
            except RuntimeError:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, run_generation())
                    result, error_type, error_msg = future.result()

            if error_type:
                print(f"[ERROR] Generation failed: {error_type} - {error_msg}")
                print(f"[ERROR] Result: {result}")
                return None
            return result

        except Exception as e:
            print(f"Generation error: {e}")
            import traceback

            traceback.print_exc()
            return None

    def submit_task(self, task_id: str) -> str:
        """Submit an existing task for processing"""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        print(f"Task submitted for processing: {task.id} - {task.name}")
        return task.id

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        return self.task_manager.cancel_task(task_id)

    def register_progress_callback(self, task_id: str, callback: Callable):
        """Register a progress callback for a task"""
        with self._callbacks_lock:
            if task_id not in self._progress_callbacks:
                self._progress_callbacks[task_id] = []
            self._progress_callbacks[task_id].append(callback)

    def unregister_progress_callback(self, task_id: str, callback: Callable):
        """Unregister a progress callback"""
        with self._callbacks_lock:
            if task_id in self._progress_callbacks:
                if callback in self._progress_callbacks[task_id]:
                    self._progress_callbacks[task_id].remove(callback)

    def _notify_progress(self, task_id: str, data: Dict[str, Any]):
        """Notify all registered callbacks"""
        with self._callbacks_lock:
            callbacks = self._progress_callbacks.get(task_id, [])

        for callback in callbacks:
            try:
                callback(task_id, data)
            except Exception as e:
                print(f"Error in progress callback: {e}")

    def get_task_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress of a task"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return None

        # Get scheduler status if available
        scheduler_status = None
        with self._schedulers_lock:
            if task_id in self._schedulers:
                scheduler_status = self._schedulers[task_id].get_status()

        # For completed tasks, also try to get the latest stats from scheduler state file
        progress = task.stats.records_generated
        if task.status == TaskStatus.COMPLETED and not scheduler_status:
            scheduler_state_path = task.get_scheduler_state_path()
            if scheduler_state_path and scheduler_state_path.exists():
                try:
                    import json
                    with open(scheduler_state_path, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                        slots = state.get('slots', [])
                        total_completed = sum(s.get('completed', 0) for s in slots)
                        total_failed = sum(s.get('failed', 0) for s in slots)
                        if total_completed > 0:
                            progress = total_completed
                except Exception:
                    pass

        return {
            "task_id": task.id,
            "status": task.status.value,
            "progress": progress,
            "total": task.config.count,
            "stats": task.stats.to_dict(),
            "scheduler_status": scheduler_status,
        }

    def get_all_progress(self) -> List[Dict[str, Any]]:
        """Get progress of all active tasks"""
        running = self.task_manager.get_running_tasks()
        pending = self.task_manager.get_pending_tasks()

        progress_list = []
        for task in running + pending:
            progress_list.append(
                {
                    "task_id": task.id,
                    "name": task.name,
                    "status": task.status.value,
                    "progress": task.stats.records_generated,
                    "total": task.config.count,
                    "stats": task.stats.to_dict(),
                }
            )

        return progress_list


# Global processor instance
_processor: Optional[TaskProcessor] = None


def get_task_processor(max_workers: int = 4) -> TaskProcessor:
    """Get or create global task processor"""
    global _processor
    if _processor is None:
        _processor = TaskProcessor(max_workers=max_workers)
        _processor.start()
    return _processor


def stop_task_processor():
    """Stop the global task processor"""
    global _processor
    if _processor:
        _processor.stop()
        _processor = None
