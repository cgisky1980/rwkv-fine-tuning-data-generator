"""V4 Web Control Center - FastAPI Backend with Task Management"""

import asyncio
import json
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    v4_path = Path(__file__).parent.parent.parent
    env_file = v4_path / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"Loaded .env from {env_file}")
except ImportError:
    print("python-dotenv not installed, using system environment variables")

# Add V4 to path
v4_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(v4_path))

from pipeline.task_manager import (
    TaskManager,
    Task,
    TaskConfig,
    TaskStatus,
    get_task_manager,
)
from pipeline.task_processor import (
    TaskProcessor,
    get_task_processor,
    stop_task_processor,
)
from pipeline.data_analyzer import DataAnalyzer
from pipeline.binidx_converter import BinidxConverter
from pipeline.export_template import export_rwkv_data as template_export_rwkv


# Pydantic models for API
class CreateTaskRequest(BaseModel):
    name: str
    generator_type: str = Field(..., pattern="^(no_tool|single_skill|single_skill_error|complex_skill|mixed_dialog|mixed)$")
    count: int = Field(..., ge=1, le=10000)
    temperature: float = Field(0.7, ge=0, le=2)
    seed: Optional[int] = None
    concurrency: int = Field(4, ge=1, le=20)
    api_key: Optional[str] = None
    user_profile_ratio: float = Field(0.3, ge=0, le=1, description="Ratio of user profile fields to fill")
    # Language ratios
    lang_ratio_zh: int = Field(70, ge=0, le=100)
    lang_ratio_en: int = Field(15, ge=0, le=100)
    lang_ratio_ja: int = Field(2, ge=0, le=100)
    lang_ratio_ko: int = Field(2, ge=0, le=100)
    lang_ratio_de: int = Field(3, ge=0, le=100)
    lang_ratio_fr: int = Field(3, ge=0, le=100)
    lang_ratio_es: int = Field(3, ge=0, le=100)
    lang_ratio_ru: int = Field(2, ge=0, le=100)
    # Topic configuration
    selected_topics: Optional[List[str]] = (
        None  # List of topic categories to include, None means all
    )
    custom_topics: Optional[List[Dict[str, Any]]] = None  # Custom topics to add
    # Custom prompts for this task
    custom_prompts: Optional[Dict[str, str]] = None  # Task-specific prompt templates
    # LLM Provider configuration
    provider_id: Optional[str] = Field(None, description="Use saved provider config")


# LLM Provider Configuration Models
class LLMProviderConfig(BaseModel):
    """LLM Provider configuration model"""

    id: str = Field(..., description="Unique provider identifier")
    name: str = Field(..., description="Provider display name")
    provider_type: str = Field(
        ...,
        description="Provider type: openrouter, deepseek, openai, azure, anthropic, etc.",
    )
    base_url: str = Field(..., description="API base URL")
    api_key: str = Field(..., description="API key (will be stored securely)")
    model: str = Field(..., description="Default model to use")
    models: Optional[List[str]] = Field(
        default=None, description="Available models list"
    )
    max_tokens: int = Field(
        default=4096, ge=1, le=100000, description="Max tokens per request"
    )
    is_default: bool = Field(
        default=False, description="Whether this is the default provider"
    )
    is_active: bool = Field(default=True, description="Whether this provider is active")


class SaveProviderRequest(BaseModel):
    """Request model for saving/updating provider"""

    id: str
    name: str
    provider_type: str
    base_url: str
    api_key: str
    model: str
    models: Optional[List[str]] = None
    max_tokens: int = 4096
    is_default: bool = False
    is_active: bool = True


class ProviderResponse(BaseModel):
    """Response model for provider (without sensitive api_key)"""

    id: str
    name: str
    provider_type: str
    base_url: str
    model: str
    models: Optional[List[str]] = None
    max_tokens: int
    is_default: bool
    is_active: bool
    has_api_key: bool  # Indicates if API key is configured (without showing it)


class ExportRequest(BaseModel):
    task_ids: List[str]
    shuffle: bool = True
    output_name: str = "v4_export"
    merge_by_type: bool = False


class TaskResponse(BaseModel):
    id: str
    name: str
    generator_type: str
    status: str
    progress: int
    total: int
    created_at: str
    updated_at: str
    stats: Dict[str, Any]


# Global instances
task_manager: TaskManager = None
task_processor: TaskProcessor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global task_manager, task_processor

    # Startup
    print("Starting V4 Task System...")
    task_manager = get_task_manager()
    task_processor = get_task_processor(max_workers=4)
    print(f"Task system ready. DB: {task_manager.db_path}")

    yield

    # Shutdown
    print("Shutting down V4 Task System...")
    stop_task_processor()
    print("Task system stopped.")


app = FastAPI(
    title="V4 Data Generator API",
    description="Advanced data generation with task management",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (frontend)
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")


# Connected WebSocket clients
websocket_clients: List[WebSocket] = []


async def broadcast_progress(task_id: str, data: Dict[str, Any]):
    """Broadcast progress to all connected WebSocket clients"""
    message = {
        "type": "progress",
        "task_id": task_id,
        "data": data,
        "timestamp": datetime.now().isoformat(),
    }

    disconnected = []
    for client in websocket_clients:
        try:
            await client.send_json(message)
        except:
            disconnected.append(client)

    # Remove disconnected clients
    for client in disconnected:
        if client in websocket_clients:
            websocket_clients.remove(client)


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    websocket_clients.append(websocket)
    print(f"WebSocket client connected. Total: {len(websocket_clients)}")

    try:
        while True:
            # Keep connection alive and handle client messages
            data = await websocket.receive_json()

            if data.get("action") == "subscribe":
                task_id = data.get("task_id")

                # Register callback for this task
                def callback(tid, progress_data):
                    asyncio.create_task(broadcast_progress(tid, progress_data))

                task_processor.register_progress_callback(task_id, callback)
                await websocket.send_json({"type": "subscribed", "task_id": task_id})

    except WebSocketDisconnect:
        websocket_clients.remove(websocket)
        print(f"WebSocket client disconnected. Total: {len(websocket_clients)}")


# Task Management API
@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(request: CreateTaskRequest):
    """Create a new generation task"""
    print(f"[API] Creating task: {request.name} (type: {request.generator_type})")

    # Build TaskConfig
    config = TaskConfig(
        generator_type=request.generator_type,
        count=request.count,
        temperature=request.temperature,
        seed=request.seed,
        concurrency=request.concurrency,
        api_key=request.api_key,
        provider_id=request.provider_id,
        user_profile_ratio=request.user_profile_ratio,
        # Language ratios
        lang_ratio_zh=request.lang_ratio_zh,
        lang_ratio_en=request.lang_ratio_en,
        lang_ratio_ja=request.lang_ratio_ja,
        lang_ratio_ko=request.lang_ratio_ko,
        lang_ratio_de=request.lang_ratio_de,
        lang_ratio_fr=request.lang_ratio_fr,
        lang_ratio_es=request.lang_ratio_es,
        lang_ratio_ru=request.lang_ratio_ru,
        # Topic configuration
        selected_topics=request.selected_topics,
        # Custom prompts
        custom_prompts=request.custom_prompts,
    )

    # Validate ratios
    valid, message = config.validate_ratios()
    if not valid:
        raise HTTPException(status_code=400, detail=message)

    # Check if task name already exists
    existing_tasks = task_manager.get_all_tasks(limit=1000)
    existing_task = next((t for t in existing_tasks if t.name == request.name), None)
    if existing_task:
        raise HTTPException(
            status_code=409,
            detail=f"Task '{request.name}' already exists (ID: {existing_task.id}, Status: {existing_task.status}). Please use a different name or delete the existing task first.",
        )

    # Create task
    try:
        task = task_manager.create_task(request.name, config)
        print(f"[API] Task created with ID: {task.id}")
    except ValueError as e:
        print(f"[API] Task creation failed: {e}")
        raise HTTPException(status_code=409, detail=str(e))

    # Submit to processor
    task_processor.submit_task(task.id)
    print(f"[API] Task submitted to processor: {task.id}")

    return TaskResponse(
        id=task.id,
        name=task.name,
        generator_type=task.generator_type,
        status=task.status.value,
        progress=0,
        total=config.count,
        created_at=task.created_at,
        updated_at=task.updated_at,
        stats=task.stats.to_dict(),
    )


@app.get("/api/tasks", response_model=List[TaskResponse])
async def list_tasks(limit: int = 100, status: Optional[str] = None):
    """List all tasks"""
    if status:
        try:
            task_status = TaskStatus(status)
            tasks = task_manager.get_tasks_by_status(task_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    else:
        tasks = task_manager.get_all_tasks(limit)

    # Helper function to get correct progress for completed tasks
    def get_progress(task):
        if task.status == TaskStatus.COMPLETED:
            # Try to get progress from scheduler state file
            scheduler_state_path = task.get_scheduler_state_path()
            if scheduler_state_path and scheduler_state_path.exists():
                try:
                    import json
                    with open(scheduler_state_path, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                        slots = state.get('slots', [])
                        total_completed = sum(s.get('completed', 0) for s in slots)
                        if total_completed > 0:
                            return total_completed
                except Exception:
                    pass
        return task.stats.records_generated

    return [
        TaskResponse(
            id=task.id,
            name=task.name,
            generator_type=task.generator_type,
            status=task.status.value,
            progress=get_progress(task),
            total=task.config.count,
            created_at=task.created_at,
            updated_at=task.updated_at,
            stats=task.stats.to_dict(),
        )
        for task in tasks
    ]


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """Get task details"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get correct progress for completed tasks
    progress = task.stats.records_generated
    if task.status == TaskStatus.COMPLETED:
        scheduler_state_path = task.get_scheduler_state_path()
        if scheduler_state_path and scheduler_state_path.exists():
            try:
                import json
                with open(scheduler_state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    slots = state.get('slots', [])
                    total_completed = sum(s.get('completed', 0) for s in slots)
                    if total_completed > 0:
                        progress = total_completed
            except Exception:
                pass

    return TaskResponse(
        id=task.id,
        name=task.name,
        generator_type=task.generator_type,
        status=task.status.value,
        progress=progress,
        total=task.config.count,
        created_at=task.created_at,
        updated_at=task.updated_at,
        stats=task.stats.to_dict(),
    )


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a task"""
    success = task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    return {"success": True, "message": "Task cancelled"}


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task and its data"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete running task")

    task_name = task.name
    success = task_manager.delete_task(task_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete task")

    return {
        "success": True,
        "message": "Task deleted",
        "name": task_name,
        "id": task_id,
    }


@app.get("/api/tasks/{task_id}/data")
async def get_task_data(task_id: str, limit: int = 100):
    """Get generated data from a task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    data_file = Path(task.data_file)
    if not data_file.exists():
        return {"records": []}

    records = []
    with open(data_file, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= limit:
                break
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return {"records": records, "total": len(records), "file": str(data_file)}


@app.get("/api/tasks/{task_id}/download")
async def download_task_data(task_id: str):
    """Download task data file"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    data_file = Path(task.data_file)
    if not data_file.exists():
        raise HTTPException(status_code=404, detail="Data file not found")

    return FileResponse(
        path=data_file, filename=f"{task_id}.jsonl", media_type="application/jsonl"
    )


# Statistics API
@app.get("/api/stats/overview")
async def get_overview_stats():
    """Get system overview statistics"""
    return task_manager.get_statistics()


@app.get("/api/stats/tasks/{task_id}")
async def get_task_stats(task_id: str):
    """Get detailed statistics for a task"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    data_file = Path(task.data_file)
    if not data_file.exists():
        return {"error": "Data file not found"}

    analysis = DataAnalyzer.analyze_task_file(data_file)
    charts = DataAnalyzer.get_distribution_chart_data(analysis)

    return {"task_id": task_id, "analysis": analysis, "charts": charts}


@app.get("/api/stats/aggregate")
async def get_aggregate_stats(task_ids: Optional[str] = None):
    """Get aggregate statistics for multiple tasks"""
    try:
        if task_ids:
            id_list = task_ids.split(",")
            files = []
            for tid in id_list:
                task = task_manager.get_task(tid)
                if task and Path(task.data_file).exists():
                    files.append(Path(task.data_file))
        else:
            # Use all completed tasks
            tasks = task_manager.get_tasks_by_status(TaskStatus.COMPLETED)
            files = [Path(t.data_file) for t in tasks if Path(t.data_file).exists()]

        if not files:
            return {"tasks_analyzed": 0, "analysis": {"total_records": 0, "total_files": 0, "languages": {}, "topics": {}, "personas": {}, "races": {}, "tool_usage": {}}, "charts": {}}

        analysis = DataAnalyzer.analyze_multiple_files(files)
        charts = DataAnalyzer.get_distribution_chart_data(analysis)

        return {"tasks_analyzed": len(files), "analysis": analysis, "charts": charts}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# Export API
@app.post("/api/export/rwkv")
async def export_rwkv(request: ExportRequest):
    """Export tasks to RWKV format using templates"""
    tasks_data = []
    total_records = 0

    for task_id in request.task_ids:
        task = task_manager.get_task(task_id)
        if not task:
            continue

        data_file = Path(task.data_file)
        if data_file.exists():
            tasks_data.append({
                'task': task,
                'data_file': data_file
            })
            total_records += task.stats.records_generated

    if not tasks_data:
        raise HTTPException(status_code=400, detail="No valid tasks to export")

    export_dir = task_manager.data_dir / "export"
    export_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = export_dir / timestamp
    output_dir.mkdir(exist_ok=True)

    if request.merge_by_type:
        tasks_by_type = {}
        for td in tasks_data:
            task = td['task']
            gen_type = task.generator_type or 'unknown'
            if gen_type not in tasks_by_type:
                tasks_by_type[gen_type] = []
            tasks_by_type[gen_type].append(td)
        
        all_exported = 0
        for gen_type, type_tasks in tasks_by_type.items():
            merged_file = output_dir / f"{gen_type}_merged.jsonl"
            with open(merged_file, "w", encoding="utf-8") as outfile:
                for td in type_tasks:
                    with open(td['data_file'], "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
            
            rwkv_file = output_dir / f"{gen_type}_rwkv.jsonl"
            num_records = template_export_rwkv(str(merged_file), str(rwkv_file))
            merged_file.unlink()
            all_exported += num_records
            
            task_ids = [td['task'].id for td in type_tasks]
            task_manager.mark_tasks_exported(task_ids, str(rwkv_file), "rwkv_template", num_records)
        
        return {
            "success": True,
            "output_dir": str(output_dir),
            "records_exported": all_exported,
            "types_exported": list(tasks_by_type.keys())
        }
    else:
        data_files = [td['data_file'] for td in tasks_data]
        merged_file = output_dir / "merged.jsonl"
        with open(merged_file, "w", encoding="utf-8") as outfile:
            for data_file in data_files:
                with open(data_file, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read())

        rwkv_file = output_dir / "rwkv.jsonl"
        num_records = template_export_rwkv(str(merged_file), str(rwkv_file))

        output_file = str(rwkv_file)
        task_manager.mark_tasks_exported(
            request.task_ids, output_file, "rwkv_template", num_records
        )

        merged_file.unlink()

        return {
            "success": True,
            "output_dir": str(output_dir),
            "records_exported": num_records,
            "tasks_exported": len(data_files),
            "format": "rwkv_template",
        }


@app.post("/api/export/preview")
async def preview_export(request: ExportRequest):
    """Preview RWKV export with first few records"""
    data_files = []

    for task_id in request.task_ids:
        task = task_manager.get_task(task_id)
        if not task:
            continue

        data_file = Path(task.data_file)
        if data_file.exists():
            data_files.append(data_file)

    if not data_files:
        raise HTTPException(status_code=400, detail="No valid tasks to export")

    export_dir = task_manager.data_dir / "export"
    export_dir.mkdir(exist_ok=True)

    merged_file = export_dir / "_preview_merged.jsonl"
    with open(merged_file, "w", encoding="utf-8") as outfile:
        for data_file in data_files:
            with open(data_file, "r", encoding="utf-8") as infile:
                for i, line in enumerate(infile):
                    if i >= 10:
                        break
                    outfile.write(line)

    preview_file = export_dir / "_preview_rwkv.jsonl"
    template_export_rwkv(str(merged_file), str(preview_file))

    previews = []
    with open(preview_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    previews.append(data.get("text", ""))
                except:
                    pass

    merged_file.unlink()
    preview_file.unlink()

    return {
        "previews": previews,
        "count": len(previews),
    }


@app.post("/api/export/binidx")
async def export_binidx(request: ExportRequest):
    """Export tasks to binidx format (no duplication)"""
    # First export to RWKV
    rwkv_result = await export_rwkv(request)

    if not rwkv_result["success"]:
        raise HTTPException(status_code=500, detail="Export failed")

    rwkv_file = Path(rwkv_result["output_file"])
    output_prefix = rwkv_file.parent / request.output_name

    # Convert to binidx
    converter = BinidxConverter()
    result = converter.convert_jsonl_to_binidx(
        rwkv_file, output_prefix, append_eod=True, verbose=True
    )

    if result["success"]:
        return {
            "success": True,
            "bin_file": result["bin_file"],
            "idx_file": result["idx_file"],
            "bin_size_mb": result["bin_size_mb"],
            "idx_size_mb": result["idx_size_mb"],
            "records_exported": rwkv_result["records_exported"],
        }
    else:
        raise HTTPException(
            status_code=500, detail=f"binidx conversion failed: {result.get('error')}"
        )


@app.get("/api/export/download/{filename}")
async def download_export(filename: str):
    """Download exported file"""
    export_dir = task_manager.data_dir / "export"
    file_path = export_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path, filename=filename, media_type="application/octet-stream"
    )


# Progress API (for polling)
@app.get("/api/progress")
async def get_all_progress():
    """Get progress of all active tasks"""
    return task_processor.get_all_progress()


@app.get("/api/progress/{task_id}")
async def get_task_progress(task_id: str):
    """Get progress of a specific task"""
    progress = task_processor.get_task_progress(task_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return progress


# Configuration API
@app.get("/api/config/languages")
async def get_language_config():
    """Get language configuration options"""
    return {
        "languages": {
            "zh": {"name": "中文", "default_ratio": 70},
            "en": {"name": "English", "default_ratio": 15},
            "ja": {"name": "日本語", "default_ratio": 2},
            "ko": {"name": "한국어", "default_ratio": 2},
            "de": {"name": "Deutsch", "default_ratio": 3},
            "fr": {"name": "Français", "default_ratio": 3},
            "es": {"name": "Español", "default_ratio": 3},
            "ru": {"name": "Русский", "default_ratio": 2},
        }
    }


# LLM Provider Configuration Storage
PROVIDERS_FILE = None  # Will be initialized in lifespan


def get_providers_file() -> Path:
    """Get the providers config file path"""
    global PROVIDERS_FILE
    if PROVIDERS_FILE is None:
        v4_path = Path(__file__).parent.parent.parent
        PROVIDERS_FILE = v4_path / "data" / "llm_providers.json"
    return PROVIDERS_FILE


def load_providers() -> Dict[str, Dict]:
    """Load all provider configurations"""
    providers_file = get_providers_file()
    if providers_file.exists():
        try:
            with open(providers_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("providers", {})
        except Exception as e:
            print(f"[Provider Config] Error loading providers: {e}")
    return {}


def save_providers(providers: Dict[str, Dict]) -> bool:
    """Save all provider configurations"""
    providers_file = get_providers_file()
    try:
        providers_file.parent.mkdir(parents=True, exist_ok=True)
        with open(providers_file, "w", encoding="utf-8") as f:
            json.dump(
                {"providers": providers, "version": "1.0"},
                f,
                ensure_ascii=False,
                indent=2,
            )
        return True
    except Exception as e:
        print(f"[Provider Config] Error saving providers: {e}")
        return False


# Predefined provider templates
PROVIDER_TEMPLATES = {
    "openrouter": {
        "name": "OpenRouter",
        "provider_type": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "openrouter/auto",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-opus",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.0-flash-exp",
            "meta-llama/llama-3.1-405b-instruct",
        ],
        "max_tokens": 16384,
    },
    "deepseek": {
        "name": "DeepSeek",
        "provider_type": "deepseek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "max_tokens": 16384,
    },
    "openai": {
        "name": "OpenAI",
        "provider_type": "openai",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "max_tokens": 16384,
    },
    "azure": {
        "name": "Azure OpenAI",
        "provider_type": "azure",
        "base_url": "",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-35-turbo"],
        "max_tokens": 16384,
    },
    "anthropic": {
        "name": "Anthropic",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ],
        "max_tokens": 16384,
    },
    "google": {
        "name": "Google Gemini",
        "provider_type": "google",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash"],
        "max_tokens": 16384,
    },
    "ollama": {
        "name": "Ollama (Local)",
        "provider_type": "ollama",
        "base_url": "http://localhost:11434/v1",
        "models": ["llama3.1", "qwen2.5", "mistral", "deepseek-r1"],
        "max_tokens": 4096,
    },
    "lmstudio": {
        "name": "LM Studio (Local)",
        "provider_type": "lmstudio",
        "base_url": "http://localhost:1234/v1",
        "models": [],
        "max_tokens": 4096,
    },
}


@app.get("/api/config/providers")
async def get_providers():
    """Get all configured LLM providers"""
    providers = load_providers()
    result = []
    for pid, p in providers.items():
        result.append(
            {
                "id": pid,
                "name": p.get("name", pid),
                "provider_type": p.get("provider_type", "custom"),
                "base_url": p.get("base_url", ""),
                "model": p.get("model", ""),
                "models": p.get("models"),
                "max_tokens": p.get("max_tokens", 4096),
                "is_default": p.get("is_default", False),
                "is_active": p.get("is_active", True),
                "has_api_key": bool(p.get("api_key")),
            }
        )
    return {"providers": result, "templates": PROVIDER_TEMPLATES}


@app.get("/api/config/providers/templates")
async def get_provider_templates():
    """Get available provider templates"""
    return {"templates": PROVIDER_TEMPLATES}


@app.post("/api/config/providers")
async def save_provider(request: SaveProviderRequest):
    """Save or update a provider configuration"""
    providers = load_providers()

    # If setting as default, unset other defaults
    if request.is_default:
        for pid, p in providers.items():
            p["is_default"] = False

    # Save provider (include api_key)
    providers[request.id] = {
        "id": request.id,
        "name": request.name,
        "provider_type": request.provider_type,
        "base_url": request.base_url,
        "api_key": request.api_key,
        "model": request.model,
        "models": request.models,
        "max_tokens": request.max_tokens,
        "is_default": request.is_default,
        "is_active": request.is_active,
    }

    if save_providers(providers):
        return {
            "success": True,
            "message": f"Provider '{request.name}' saved successfully",
            "id": request.id,
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save provider")


@app.delete("/api/config/providers/{provider_id}")
async def delete_provider(provider_id: str):
    """Delete a provider configuration"""
    providers = load_providers()

    if provider_id not in providers:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )

    provider_name = providers[provider_id].get("name", provider_id)
    del providers[provider_id]

    if save_providers(providers):
        return {
            "success": True,
            "message": f"Provider '{provider_name}' deleted",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to delete provider")


@app.post("/api/config/providers/{provider_id}/set-default")
async def set_default_provider(provider_id: str):
    """Set a provider as the default"""
    providers = load_providers()

    if provider_id not in providers:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )

    # Unset all defaults
    for pid in providers:
        providers[pid]["is_default"] = False

    # Set new default
    providers[provider_id]["is_default"] = True

    if save_providers(providers):
        return {
            "success": True,
            "message": f"Provider '{providers[provider_id]['name']}' is now the default",
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to set default provider")


@app.get("/api/config/providers/{provider_id}")
async def get_provider(provider_id: str):
    """Get a specific provider configuration (with API key)"""
    providers = load_providers()

    if provider_id not in providers:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )

    p = providers[provider_id]
    return {
        "id": provider_id,
        "name": p.get("name", provider_id),
        "provider_type": p.get("provider_type", "custom"),
        "base_url": p.get("base_url", ""),
        "api_key": p.get("api_key", ""),
        "model": p.get("model", ""),
        "models": p.get("models"),
        "max_tokens": p.get("max_tokens", 4096),
        "is_default": p.get("is_default", False),
        "is_active": p.get("is_active", True),
    }


@app.post("/api/config/providers/{provider_id}/test")
async def test_provider(provider_id: str):
    """Test provider connection"""
    providers = load_providers()

    if provider_id not in providers:
        raise HTTPException(
            status_code=404, detail=f"Provider '{provider_id}' not found"
        )

    p = providers[provider_id]

    from pipeline.common import LLMClient
    import asyncio
    import concurrent.futures
    import json

    try:
        client = LLMClient(
            api_key=p.get("api_key", ""),
            base_url=p.get("base_url", ""),
            model=p.get("model", ""),
        )

        test_prompt = "Respond with a JSON object containing a single field 'status' with value 'ok'."

        async def _test():
            try:
                result = await client.generate(test_prompt, max_tokens=100, json_mode=True)
                try:
                    json.loads(result)
                    return {"success": True, "json_supported": True, "response": result[:100]}
                except json.JSONDecodeError:
                    return {"success": True, "json_supported": False, "response": result[:100]}
            except Exception as e:
                error_msg = str(e)
                # Also check response text for embedded error messages
                if hasattr(e, 'response') and e.response:
                    try:
                        error_data = e.response.json()
                        raw_error = error_data.get("error", {}).get("metadata", {}).get("raw", "")
                        if "json_object is not supported" in raw_error:
                            return {"success": True, "json_supported": False, "response": "", "error": "json_object not supported"}
                    except:
                        pass
                if "json_object is not supported" in error_msg:
                    return {"success": True, "json_supported": False, "response": "", "error": "json_object not supported"}
                raise e

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _test())
            test_result = future.result()

        result = test_result.get("response", "")
        
        if test_result.get("json_supported") == False:
            from pipeline.common import update_provider_supports_json_object
            update_provider_supports_json_object(provider_id, False)
            message = "Provider connected, but json_object not supported (auto-disabled)"
        else:
            message = "Provider connection successful"

        return {
            "success": True,
            "message": message,
            "test_result": result if result else test_result.get("error", "No response"),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
        }


class TopicRequest(BaseModel):
    parent_key: Optional[str] = None  # null for new category
    new_parent_name: Optional[str] = None  # required if parent_key is null
    topic_name: str
    topic_description: Optional[str] = ""


@app.get("/api/config/topics")
async def get_topics():
    """Get all available topics from configuration (tree structure)"""
    v4_path = Path(__file__).parent.parent.parent
    topics_file = v4_path / "data" / "chat_topics.json"

    categories = []
    if topics_file.exists():
        with open(topics_file, "r", encoding="utf-8") as f:
            topics_data = json.load(f)

        # Support both formats: categories array or topics array
        categories = topics_data.get("categories", [])
        if not categories:
            # Convert topics array to categories format for frontend
            topics_list = topics_data.get("topics", [])
            for topic in topics_list:
                category_name = topic.get("category", "unknown")
                # Convert levels to topics format
                topics_in_cat = []
                levels = topic.get("levels", {})
                for level_key, level_info in levels.items():
                    topics_in_cat.append({
                        "key": f"{category_name}_{level_key}",
                        "name": level_info.get("topic", level_key),
                        "description": level_info.get("dialogue_pattern", ""),
                    })
                
                categories.append({
                    "key": category_name,
                    "name": category_name,
                    "description": topic.get("description", ""),
                    "topics": topics_in_cat,
                })

    return {"categories": categories}


def _generate_topic_key(category: str) -> str:
    """Generate English key from Chinese category name"""
    import re

    # Simple pinyin-like conversion or transliteration
    # For now, use a mapping for common Chinese characters
    char_map = {
        "主题": "theme",
        "氛围": "atmosphere",
        "文件": "file",
        "管理": "management",
        "消息": "message",
        "发送": "sending",
        "系统": "system",
        "操作": "operation",
        "文件夾": "folder",
        "应用": "app",
        "启动": "launch",
        "待办": "todo",
        "脚本": "script",
        "执行": "execution",
        "综合": "comprehensive",
        "使用": "usage",
        "日常": "daily",
        "闲聊": "chat",
        "知识": "knowledge",
        "问答": "qa",
        "情感": "emotional",
        "陪伴": "support",
        "健身": "fitness",
        "指导": "guide",
        "旅游": "travel",
        "规划": "planning",
        "学习": "study",
        "工作": "work",
        "生活": "life",
        "娱乐": "entertainment",
        "健康": "health",
        "饮食": "diet",
        "编程": "programming",
        "游戏": "gaming",
        "音乐": "music",
        "电影": "movie",
        "阅读": "reading",
        "运动": "sports",
        "购物": "shopping",
        "烹饪": "cooking",
    }

    # Try to map common patterns
    result = category.lower()
    for cn, en in char_map.items():
        result = result.replace(cn, en)

    # Remove non-alphanumeric characters and convert to snake_case
    result = re.sub(r"[^\w\s]", "", result)
    result = re.sub(r"\s+", "_", result.strip())

    # If empty or too short, use a fallback
    if len(result) < 3:
        result = "topic_" + re.sub(r"[^\w]", "", category)

    return result


@app.post("/api/config/topics")
async def add_topic(request: TopicRequest):
    """Add a new topic category with automatic key generation"""
    v4_path = Path(__file__).parent.parent.parent

    # 1. Update chat_topics.json (tree structure)
    topics_file = v4_path / "data" / "chat_topics.json"
    topics_data = {}
    if topics_file.exists():
        with open(topics_file, "r", encoding="utf-8") as f:
            topics_data = json.load(f)

    if "categories" not in topics_data:
        topics_data["categories"] = []

    categories = topics_data["categories"]

    # Determine parent category
    parent_category = None
    if request.parent_key:
        # Find existing category
        for cat in categories:
            if cat.get("key") == request.parent_key:
                parent_category = cat
                break
        if not parent_category:
            raise HTTPException(
                status_code=404,
                detail=f"Parent category '{request.parent_key}' not found",
            )
    elif request.new_parent_name:
        # Create new category
        cat_key = _generate_topic_key(request.new_parent_name)
        # Ensure unique key
        existing_cat_keys = {c.get("key", "") for c in categories}
        counter = 1
        base_cat_key = cat_key
        while cat_key in existing_cat_keys:
            cat_key = f"{base_cat_key}_{counter}"
            counter += 1

        parent_category = {
            "key": cat_key,
            "name": request.new_parent_name,
            "topics": [],
        }
        categories.append(parent_category)
    else:
        raise HTTPException(
            status_code=400, detail="Either parent_key or new_parent_name is required"
        )

    # Generate unique topic key
    topic_key = _generate_topic_key(request.topic_name)
    # Collect all existing topic keys
    existing_topic_keys = set()
    for cat in categories:
        for topic in cat.get("topics", []):
            existing_topic_keys.add(topic.get("key", ""))

    counter = 1
    base_topic_key = topic_key
    while topic_key in existing_topic_keys:
        topic_key = f"{base_topic_key}_{counter}"
        counter += 1

    # Add new topic to parent category
    new_topic = {
        "key": topic_key,
        "name": request.topic_name,
        "description": request.topic_description,
    }

    if "topics" not in parent_category:
        parent_category["topics"] = []
    parent_category["topics"].append(new_topic)

    # Save to file
    with open(topics_file, "w", encoding="utf-8") as f:
        json.dump(topics_data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": f"Topic '{request.topic_name}' added successfully under '{parent_category['name']}'",
        "topic": new_topic,
        "restart_required": True,
    }


@app.delete("/api/config/topics/{category_key}/{topic_key}")
async def delete_topic(category_key: str, topic_key: str):
    """Delete a topic from a category"""
    v4_path = Path(__file__).parent.parent.parent
    topics_file = v4_path / "data" / "chat_topics.json"

    if not topics_file.exists():
        raise HTTPException(status_code=404, detail="Topics file not found")

    with open(topics_file, "r", encoding="utf-8") as f:
        topics_data = json.load(f)

    categories = topics_data.get("categories", [])

    # Find category and remove topic
    for cat in categories:
        if cat.get("key") == category_key:
            original_len = len(cat.get("topics", []))
            cat["topics"] = [
                t for t in cat.get("topics", []) if t.get("key") != topic_key
            ]
            if len(cat["topics"]) == original_len:
                raise HTTPException(
                    status_code=404,
                    detail=f"Topic '{topic_key}' not found in category '{category_key}'",
                )

            # Save to file
            with open(topics_file, "w", encoding="utf-8") as f:
                json.dump(topics_data, f, ensure_ascii=False, indent=2)

            return {
                "success": True,
                "message": f"Topic '{topic_key}' deleted successfully",
            }

    raise HTTPException(status_code=404, detail=f"Category '{category_key}' not found")


@app.get("/api/config/generators/{generator_id}/template")
async def get_generator_template(generator_id: str):
    """Get template content for a generator"""
    v4_path = Path(__file__).parent.parent.parent
    generators_path = v4_path / "generators"

    generator_file = generators_path / generator_id / "generator.yaml"
    if not generator_file.exists():
        raise HTTPException(
            status_code=404, detail=f"Generator '{generator_id}' not found"
        )

    with open(generator_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    template_path_str = config.get("template", "")
    if not template_path_str:
        return {"content": "", "name": config.get("name", generator_id)}

    # Template path is relative to the generator folder
    template_path = generators_path / generator_id / template_path_str
    if template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""

    return {
        "content": content,
        "name": config.get("name", generator_id),
    }


class GeneratorCreateRequest(BaseModel):
    id: str
    name: str
    description: str
    template: str = ""
    tools: List[Dict[str, Any]] = []
    persona_enabled: bool = True
    user_profile_enabled: bool = True
    tts_enabled: bool = True
    topic_enabled: bool = True
    content: str = ""


class GeneratorUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    persona_enabled: Optional[bool] = None
    user_profile_enabled: Optional[bool] = None
    tts_enabled: Optional[bool] = None
    topic_enabled: Optional[bool] = None
    output_schema: Optional[Dict[str, Any]] = None
    content: Optional[str] = None


@app.get("/api/admin/generators")
async def list_generators():
    """List all generators - auto-scan from directory"""
    from pipeline import get_generator_loader
    
    loader = get_generator_loader()
    generators = []
    
    for gen_info in loader._generators.values():
        config = loader.get_generator(gen_info.id) or {}
        generators.append(
            {
                "id": gen_info.id,
                "name": gen_info.name,
                "description": gen_info.description,
                "path": str(gen_info.path.relative_to(loader.base_path)),
                "enabled": gen_info.enabled,
                "default": gen_info.default,
                "template": config.get("template", ""),
                "tools_count": len(config.get("tools", [])),
            }
        )
    
    return {"generators": generators}


@app.get("/api/admin/generators/{generator_id}")
async def get_generator(generator_id: str):
    """Get generator full config"""
    import re
    from pipeline import get_generator_loader
    
    loader = get_generator_loader()
    gen_info = loader._generators.get(generator_id)
    
    if not gen_info:
        raise HTTPException(status_code=404, detail=f"Generator '{generator_id}' not found")
    
    config = loader.get_generator(generator_id) or {}
    
    template_content = ""
    template_path = loader.get_template_path(generator_id)
    if template_path and template_path.exists():
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
    
    output_schema = config.get("output_schema", {})
    if not output_schema and template_content:
        match = re.search(r'##\s*输出格式\s*```json\s*(\[[\s\S]*?\])\s*```', template_content)
        if match:
            try:
                example_array = json.loads(match.group(1))
                if example_array and len(example_array) > 0:
                    sample_item = example_array[0]
                    properties = {}
                    required = []
                    for key, value in sample_item.items():
                        field_type = "string"
                        if isinstance(value, bool):
                            field_type = "boolean"
                        elif isinstance(value, int):
                            field_type = "integer"
                        elif isinstance(value, float):
                            field_type = "number"
                        properties[key] = {
                            "type": field_type,
                            "description": str(value) if value else ""
                        }
                        required.append(key)
                    output_schema = {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
            except:
                pass
    
    return {
        "id": generator_id,
        "name": gen_info.name,
        "description": gen_info.description,
        "path": str(gen_info.path.relative_to(loader.base_path)),
        "enabled": gen_info.enabled,
        "default": gen_info.default,
        "template": config.get("template", ""),
        "template_content": template_content,
        "tools": config.get("tools", []),
        "persona": config.get("persona", {}),
        "user_profile": config.get("user_profile", {}),
        "tts": config.get("tts", {}),
        "topic": config.get("topic", {}),
        "levels": config.get("levels", {}),
        "parameters": config.get("parameters", {}),
        "rules": config.get("rules", {}),
        "output_schema": output_schema,
    }


@app.post("/api/admin/generators")
async def create_generator(request: GeneratorCreateRequest):
    """Create a new generator"""
    from pipeline import reload_generator_loader
    
    v4_path = Path(__file__).parent.parent.parent
    generators_path = v4_path / "generators"

    if not request.id.isalnum() and not request.id.replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="Generator ID must be alphanumeric (underscore allowed)",
        )

    gen_dir = generators_path / request.id
    if gen_dir.exists():
        raise HTTPException(
            status_code=409, detail=f"Generator '{request.id}' already exists"
        )

    gen_dir.mkdir(exist_ok=True)
    templates_dir = gen_dir / "templates"
    templates_dir.mkdir(exist_ok=True)

    template_file = templates_dir / "main.j2"
    with open(template_file, "w", encoding="utf-8") as f:
        f.write(request.content or "# Template for " + request.name)

    config = {
        "id": request.id,
        "name": request.name,
        "description": request.description,
        "template": "templates/main.j2",
        "persona": {
            "enabled": request.persona_enabled,
            "fields": ["name", "gender", "age", "race", "tone"],
            "lang_style": True,
            "race_style": True,
        },
        "user_profile": {
            "enabled": request.user_profile_enabled,
            "random_known_fields": True,
            "fields": ["name", "age", "gender", "location", "occupation", "hobbies"],
        },
        "system": {
            "birthday": True,
            "time_context": True,
        },
        "tts": {
            "enabled": request.tts_enabled,
            "format": "{V:说话风格描述,A:动作} 说话内容",
            "per_sentence": True,
            "description": "用生活化语言描述说话风格，完全由LLM自由生成",
        },
        "topic": {
            "enabled": request.topic_enabled,
            "source": "data/chat_topics.json",
        },
        "tools": request.tools,
        "parameters": {
            "min_turns": 3,
            "max_turns": 8,
            "require_tools": len(request.tools) > 0,
        },
        "rules": [
            "每句话必须以 {V:说话风格描述,A:动作} 开头",
            "respond 使用 persona 指定的语言",
        ],
    }

    gen_file = gen_dir / "generator.yaml"
    with open(gen_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    reload_generator_loader()

    return {
        "success": True,
        "id": request.id,
        "message": f"Generator '{request.id}' created successfully",
        "generator": {"id": request.id, "name": request.name},
    }


@app.put("/api/admin/generators/{generator_id}")
async def update_generator(generator_id: str, request: GeneratorUpdateRequest):
    """Update generator config"""
    from pipeline import get_generator_loader, reload_generator_loader
    
    loader = get_generator_loader()
    gen_info = loader._generators.get(generator_id)
    
    if not gen_info:
        raise HTTPException(status_code=404, detail=f"Generator '{generator_id}' not found")
    
    config = loader.get_generator(generator_id) or {}
    
    if request.name is not None:
        config["name"] = request.name
    if request.description is not None:
        config["description"] = request.description
    if request.template is not None:
        config["template"] = request.template
    if request.tools is not None:
        config["tools"] = request.tools
    if request.persona_enabled is not None:
        if "persona" not in config:
            config["persona"] = {}
        config["persona"]["enabled"] = request.persona_enabled
    if request.user_profile_enabled is not None:
        if "user_profile" not in config:
            config["user_profile"] = {}
        config["user_profile"]["enabled"] = request.user_profile_enabled
    if request.tts_enabled is not None:
        if "tts" not in config:
            config["tts"] = {}
        config["tts"]["enabled"] = request.tts_enabled
    if request.topic_enabled is not None:
        if "topic" not in config:
            config["topic"] = {}
        config["topic"]["enabled"] = request.topic_enabled
    if request.enabled is not None:
        gen_info.enabled = request.enabled
    if request.default is not None:
        for g in loader._generators.values():
            g.default = False
        gen_info.default = request.default
    
    if request.output_schema is not None:
        config["output_schema"] = request.output_schema

    with open(gen_info.path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    
    reload_generator_loader()
    
    return {"success": True, "message": f"Generator '{generator_id}' updated"}


@app.delete("/api/admin/generators/{generator_id}")
async def delete_generator(generator_id: str):
    """Delete a generator"""
    from pipeline import get_generator_loader, reload_generator_loader
    
    loader = get_generator_loader()
    gen_info = loader._generators.get(generator_id)
    
    if not gen_info:
        raise HTTPException(status_code=404, detail=f"Generator '{generator_id}' not found")
    
    if gen_info.default:
        raise HTTPException(status_code=400, detail="Cannot delete the default generator")
    
    import shutil
    gen_dir = gen_info.path.parent
    if gen_dir.exists():
        shutil.rmtree(gen_dir)
    
    reload_generator_loader()
    
    return {"success": True, "message": f"Generator '{generator_id}' deleted"}


@app.put("/api/admin/generators/{generator_id}/template")
async def update_generator_template(generator_id: str, request: dict):
    """Update generator template content"""
    from pipeline import get_generator_loader
    
    loader = get_generator_loader()
    gen_info = loader._generators.get(generator_id)
    
    if not gen_info:
        raise HTTPException(status_code=404, detail=f"Generator '{generator_id}' not found")
    
    content = request.get("content", "")
    template_path = loader.get_template_path(generator_id)
    
    if template_path and template_path.exists():
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(content)
    
    return {"success": True, "message": f"Template for '{generator_id}' updated"}


@app.post("/api/admin/generators/{generator_id}/toggle")
async def toggle_generator(generator_id: str, request: dict):
    """Enable or disable a generator"""
    from pipeline import get_generator_loader, reload_generator_loader
    
    loader = get_generator_loader()
    gen_info = loader._generators.get(generator_id)
    
    if not gen_info:
        raise HTTPException(status_code=404, detail=f"Generator '{generator_id}' not found")
    
    enabled = request.get("enabled", not gen_info.enabled)
    gen_info.enabled = enabled
    
    config = loader.get_generator(generator_id) or {}
    with open(gen_info.path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False)
    
    reload_generator_loader()
    
    status = "enabled" if enabled else "disabled"
    return {"success": True, "message": f"Generator '{generator_id}' {status}"}


class TestGeneratorRequest(BaseModel):
    template_content: str
    call_api: bool = False  # 是否调用 API 进行真实测试
    api_key: Optional[str] = None
    base_url: Optional[str] = "https://api.deepseek.com"
    model: Optional[str] = "deepseek-chat"
    temperature: float = 0.7
    seed: Optional[int] = None


@app.post("/api/admin/generators/test")
async def test_generator(request: TestGeneratorRequest):
    """Test a generator template with sample data and optionally call DeepSeek API"""
    from jinja2 import Template, TemplateSyntaxError, Environment, FileSystemLoader
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from pipeline.common import LLMClient
    import json

    # Sample variables for testing - 包含所有模板变量
    sample_vars = {
        "topic": "日常生活",
        "persona_name": "小美",
        "persona_race": "猫娘",
        "persona_gender": "女",
        "persona_personality": "温柔体贴，善于倾听",
        "persona_tone": "温柔",
        "verbal_tics": "喵~、呼噜、会好的",
        "user_title": "主人",
        "language": "中文",
        "user_language": "中文",
        "assistant_language": "中文",
        "user_profile": {
            "name": "小明",
            "age": "30",
            "gender": "未知",
            "location": "未知",
            "occupation": "未知",
            "hobbies": "未知",
            "known_fields": {"name": "小明", "age": "30"},
        },
        "user_profile_ref": {},
        "turn_count": 3,
        "id": "test-uuid-1234",
        "datetime": "2024-01-15 14:30:00",
        "weekday": "星期一",
        "tts": {
            "enabled": True,
            "format": "(情绪+语速+语调, 动作) 说话内容",
            "emotions": ["开心", "难过", "生气", "平静"],
            "speeds": ["快速", "缓慢", "正常"],
            "tones": ["说", "低语", "问"],
        },
        "persona": {
            "name": "小美",
            "gender": "女",
            "language": "中文",
            "race": "猫娘",
            "personality": "温柔体贴",
            "tone": "温柔",
            "identity": "猫娘",
            "user_title": "主人",
            "optional_tics": {"中文": ["喵~", "呼噜"]},
        },
        "time_context": {
            "time": "14:30",
            "weekday": "星期一",
            "weather": "晴朗",
            "date": "2024-01-15",
        },
        "birthday": "2020-01-01",
        "parameters": {
            "min_turns": 3,
            "max_turns": 8,
            "require_tools": False,
        },
        "output_format": {
            "schema": """[
  {
    "role": "user",
    "say": "string - 用户消息",
    "refs": "string - 用户提供的参考背景资料，可为空"
  },
  {
    "role": "assistant",
    "respond": "string - 助手回复，每句以TTS指令开头"
  }
]""",
            "notes": [
                "不要使用 `thought` 字段",
                "每句话都要以 TTS 指令开头",
                "refs 字段可选，可以为空字符串",
            ],
        },
    }

    try:
        # Try with FileSystemLoader if template contains imports
        if "{% import" in request.template_content or "{% include" in request.template_content:
            v4_path = Path(__file__).parent.parent.parent
            # Find template directory from config or use default
            template_dir = v4_path / "generators" / "no_tool" / "templates"
            env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=False
            )
            # Add template directory to the search path for imports
            env.loader.searchpath = [str(template_dir)]
            template = env.from_string(request.template_content)
            rendered = template.render(**sample_vars)
        else:
            template = Template(request.template_content)
            rendered = template.render(**sample_vars)

        result = {
            "success": True,
            "rendered": rendered,
            "sample_variables": sample_vars,
        }

        # 只有请求 call_api 时才调用 DeepSeek API
        if request.call_api:
            import os

            api_key = (
                request.api_key
                if request.api_key and request.api_key.strip()
                else os.getenv("DEEPSEEK_API_KEY")
            )

            if api_key and api_key.strip():
                try:
                    llm = LLMClient(
                        api_key=api_key or "",
                        base_url=request.base_url or "https://api.deepseek.com",
                        model=request.model or "deepseek-chat",
                    )

                    response = await llm.generate(
                        rendered,
                        temperature=request.temperature,
                        max_tokens=2000,
                        json_mode=True,
                    )

                    # 尝试解析 JSON 响应
                    try:
                        # 尝试从响应中提取 JSON
                        json_str = response
                        if "```json" in response:
                            json_str = (
                                response.split("```json")[1].split("```")[0].strip()
                            )
                        elif "```" in response:
                            json_str = response.split("```")[1].split("```")[0].strip()

                        generated_data = json.loads(json_str)
                        result["generated_data"] = generated_data
                        result["raw_response"] = response

                    except json.JSONDecodeError:
                        # 如果无法解析为 JSON，返回原始响应
                        result["raw_response"] = response
                        result["parse_error"] = "无法解析为 JSON 格式"

                    await llm.close()

                except Exception as api_error:
                    result["api_error"] = str(api_error)
            else:
                result["api_skipped"] = (
                    "未配置 API key，请在 .env 文件中设置 DEEPSEEK_API_KEY"
                )

        return result

    except TemplateSyntaxError as e:
        return {
            "success": False,
            "error_type": "syntax_error",
            "error_message": f"模板语法错误: {e.message} (行 {e.lineno})",
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": "render_error",
            "error_message": str(e),
        }


class SavePromptsRequest(BaseModel):
    templates: Dict[str, Dict[str, Any]]


@app.get("/api/config/prompts")
async def get_prompt_templates():
    """Get all prompt templates"""
    v4_path = Path(__file__).parent.parent.parent
    prompts_file = v4_path / "data" / "prompts_config.json"

    if not prompts_file.exists():
        return {"templates": {}, "version": "4.0", "variables": []}

    with open(prompts_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "templates": data.get("templates", {}),
        "version": data.get("version", "4.0"),
        "variables": data.get("variables", {}).get("list", []),
    }


@app.post("/api/config/prompts")
async def save_prompt_templates(request: SavePromptsRequest):
    """Save all prompt templates"""
    v4_path = Path(__file__).parent.parent.parent
    prompts_file = v4_path / "data" / "prompts_config.json"

    data = {
        "version": "4.0",
        "last_updated": datetime.now().isoformat() + "Z",
        "templates": request.templates,
        "variables": {
            "description": "提示词中可用的变量",
            "list": [
                {"name": "{topic}", "description": "对话话题"},
                {"name": "{persona_name}", "description": "助手名称"},
                {"name": "{persona_tone}", "description": "助手性格"},
                {"name": "{persona_json}", "description": "完整 Persona JSON"},
                {"name": "{user_profile}", "description": "用户画像信息"},
                {"name": "{user_query}", "description": "用户问题"},
                {"name": "{tools_json}", "description": "可用工具 JSON"},
                {"name": "{refs_json}", "description": "参考信息 JSON"},
                {"name": "{turn_count}", "description": "对话轮数"},
                {"name": "{datetime}", "description": "时间戳"},
                {"name": "{weekday}", "description": "星期几"},
                {"name": "{weather}", "description": "天气"},
                {"name": "{birthday}", "description": "助手生日"},
                {"name": "{id}", "description": "样本 ID"},
                {"name": "{level}", "description": "难度级别"},
                {"name": "{language}", "description": "语言代码"},
            ],
        },
    }

    with open(prompts_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": "Prompt templates saved successfully",
        "version": data["version"],
    }


@app.post("/api/config/prompts/reset")
async def reset_prompt_templates():
    """Reset prompt templates to default"""
    v4_path = Path(__file__).parent.parent.parent
    prompts_file = v4_path / "data" / "prompts_config.json"

    default_templates = {
        "no_tool": {
            "name": "无工具对话模板",
            "description": "用于生成纯对话数据，无需工具调用",
            "content": 'You are a synthetic data generator.\nGenerate a realistic multi-turn conversation between a User and an Assistant.\n\n## V4 Requirements\n1. **NO THOUGHT FIELD**: Assistant responses must NOT include a \'thought\' field. Output direct responses only.\n2. **Natural Language TTS Format**: Every sentence must start with natural language instruction in parentheses.\n\n## TTS Instruction Format (Natural Language)\nFormat: `(情绪+语速+语调, 动作) 说话内容`\n\nComponents:\n- **情绪**: 开心、难过、生气、平静、兴奋、惊讶、悲伤、温柔、严肃、俏皮、尴尬、疲惫\n- **语速**: 快速、缓慢、正常、飞快、慢慢、从容\n- **语调/方式**: 说、低语、问、解释、宣布、讨论\n- **动作**: 挥手、点头、摇头、耸肩、微笑、皱眉、眨眼、鼓掌、思考、指向、鞠躬、叉腰、抱臂、无\n\n## JSON Structure\n[\n  {"role": "user", "say": "用户消息"},\n  {"role": "assistant", "respond": "(开心地快速说, 挥手) 助手回复"}\n]\n\n## User Dialogue Requirements\n- User messages must be NATURAL and VARIED\n- User should initiate conversation based on the topic context\n- Vary message length: sometimes short (1-2 words), sometimes longer\n- User can use casual language, slang, or formal speech depending on context\n\n## Rules\n- Every sentence in `respond` MUST start with `(情绪+语速+语调, 动作)` format\n- Generate varied emotions based on context\n- No thought field in output\n- Natural conversation flow\n\n## Context\n- **Topic**: {topic}\n- **Persona**: {persona_name} ({persona_tone})\n- **User Profile**: {user_profile}\n\nGenerate a {turn_count}-turn conversation.',
        },
        "tool": {
            "name": "工具对话模板",
            "description": "用于生成需要工具调用的对话数据",
            "content": 'You are a synthetic data generator.\nUser Query: "{user_query}"\n\n## Available Tools\n{tools_json}\n\n## Reference Info\n{refs_json}\n\n## Task\nGenerate the assistant\'s response process including Thought, Tool Calls, and Final Response.\n\n## V4 TTS Format\nEvery response must use natural language TTS instruction format:\n`(情绪+语速+语调, 动作) 说话内容`\n\n## JSON Structure\n{{\n  "thought": [\n    {{ "observation": "...", "reasoning": "...", "reflection": "...", "action": "..." }}\n  ],\n  "tool_calls": [\n    {{\n      "step": 1,\n      "tool_respond": "(友好地正常说, 点头) 我这就为您查询。",\n      "tool_call": {{ "name": "...", "arguments": {{ ... }} }},\n      "tool_risk": true,\n      "tool_output": {{ ... }}\n    }}\n  ],\n  "respond": "(开心地快速说, 挥手) 这是查询结果..."\n}}\n\n## CRITICAL RULES\n\n### 1. Tool Risk Control\n- If `force_refusal=true`, simulate a HIGH-RISK tool call that the User REJECTS.\n- Set `tool_risk` to `false` when user rejects.\n- When `tool_risk=false`, **MUST OMIT** the `tool_output` field entirely.\n\n### 2. tool_respond Constraint\n- `tool_respond` describes what the assistant is ABOUT TO DO.\n- **MUST NOT** include any tool results or predictions.\n\n### 3. TTS Format\n- Use `(情绪+语速+语调, 动作)` format for ALL responses.\n\n## Force Refusal Setting\nForce Refusal Mode: {force_refusal}\n\n## Persona\n{persona_json}\n\n## Rules\n- Every sentence in `respond` MUST start with TTS instruction format\n',
        },
        "system": {
            "name": "系统提示词",
            "description": "系统级提示词配置",
            "content": '{{\n  "id": "{id}",\n  "level": "{level}",\n  "language": "{language}",\n  "topic": "{topic}",\n  "system": {{\n    "persona": {persona},\n    "user_profile": "{user_profile}",\n    "time_context": {{\n      "datetime": "{datetime}",\n      "weekday": "{weekday}",\n      "weather": "{weather}"\n    }},\n    "birthday": "{birthday}"\n  }},\n  "turns": {turns}\n}}}}',
        },
    }

    data = {
        "version": "4.0",
        "last_updated": datetime.now().isoformat() + "Z",
        "templates": default_templates,
        "variables": {
            "description": "提示词中可用的变量",
            "list": [
                {"name": "{topic}", "description": "对话话题"},
                {"name": "{persona_name}", "description": "助手名称"},
                {"name": "{persona_tone}", "description": "助手性格"},
                {"name": "{persona_json}", "description": "完整 Persona JSON"},
                {"name": "{user_profile}", "description": "用户画像信息"},
                {"name": "{user_query}", "description": "用户问题"},
                {"name": "{tools_json}", "description": "可用工具 JSON"},
                {"name": "{refs_json}", "description": "参考信息 JSON"},
                {"name": "{turn_count}", "description": "对话轮数"},
                {"name": "{datetime}", "description": "时间戳"},
                {"name": "{weekday}", "description": "星期几"},
                {"name": "{weather}", "description": "天气"},
                {"name": "{birthday}", "description": "助手生日"},
                {"name": "{id}", "description": "样本 ID"},
                {"name": "{level}", "description": "难度级别"},
                {"name": "{language}", "description": "语言代码"},
            ],
        },
    }

    with open(prompts_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": "Prompt templates reset to default",
        "version": data["version"],
    }


@app.get("/api/config/generators")
async def get_generators():
    """Get available generators"""
    try:
        from pipeline import list_available_generators

        generators = list_available_generators()
        return {"generators": generators}
    except Exception as e:
        return {"generators": [], "error": str(e)}


# Root endpoint - serve frontend
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the frontend HTML"""
    index_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse(
        content="<h1>V4 Data Generator</h1><p>Frontend not found. Please check installation.</p>",
        status_code=404,
    )


# API info endpoint
@app.get("/api")
async def api_info():
    """API info"""
    return {
        "message": "V4 Data Generator API v2.0",
        "features": [
            "Task Management",
            "Real-time Progress (WebSocket)",
            "Data Statistics",
            "RWKV Export",
            "binidx Conversion",
        ],
        "endpoints": {
            "tasks": "/api/tasks",
            "stats": "/api/stats/overview",
            "export": "/api/export/rwkv",
            "websocket": "/ws",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
