"""
独立数据生成 Skill — 配置管理
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None


DEFAULT_CONFIG = {
    "db_path": "data/gen_data.db",
    "work_item_timeout_seconds": 600,
    "max_retries": 3,
    "batch_size": 5,
    "generators_dir": "../generators",
    "v4_data_dir": "../data",
}


class Config:
    def __init__(self, config_path: Optional[str] = None):
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        if config_path and os.path.exists(config_path):
            self._load_file(config_path)
        self._apply_env_overrides()

    def _load_file(self, path: str):
        if yaml is None:
            return
        with open(path, "r", encoding="utf-8") as f:
            file_data = yaml.safe_load(f) or {}
        self._data.update(file_data)

    def _apply_env_overrides(self):
        env_map = {
            "DGS_DB_PATH": "db_path",
            "DGS_WORK_TIMEOUT": "work_item_timeout_seconds",
            "DGS_MAX_RETRIES": "max_retries",
        }
        for env_key, config_key in env_map.items():
            val = os.environ.get(env_key)
            if val:
                self._data[config_key] = int(val) if config_key != "db_path" else val

    @property
    def db_path(self) -> str:
        return self._data.get("db_path", "data/gen_data.db")

    @property
    def work_item_timeout_seconds(self) -> int:
        return int(self._data.get("work_item_timeout_seconds", 600))

    @property
    def max_retries(self) -> int:
        return int(self._data.get("max_retries", 3))

    @property
    def batch_size(self) -> int:
        return int(self._data.get("batch_size", 5))

    @property
    def generators_dir(self) -> str:
        return self._data.get("generators_dir", "../generators")

    @property
    def v4_data_dir(self) -> str:
        return self._data.get("v4_data_dir", "../data")

    def resolve_db_path(self, base_dir: Path) -> Path:
        return base_dir / self.db_path

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)


_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config