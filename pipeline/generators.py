"""
V4 生成器加载器

负责加载和管理所有生成器配置。
自动扫描 generators 目录下的每个子目录。
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class GeneratorInfo:
    """生成器信息"""

    id: str
    name: str
    description: str
    path: Path
    enabled: bool = True
    default: bool = False


@dataclass
class ToolDefinition:
    """工具定义"""

    name: str
    description: str
    alias: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk: str = "low"
    help: str = ""


class GeneratorLoader:
    """生成器配置加载器 - 自动扫描目录"""

    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path(__file__).parent.parent / "generators"
        self._generators: Dict[str, GeneratorInfo] = {}
        self._configs: Dict[str, Dict] = {}
        self._scan_generators()

    def _scan_generators(self):
        """自动扫描 generators 目录下的所有生成器"""
        if not self.base_path.exists():
            return

        for item in self.base_path.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith("_") or item.name.startswith("."):
                continue
            
            config_file = item / "generator.yaml"
            if not config_file.exists():
                continue

            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                
                gen_id = config.get("id", item.name)
                info = GeneratorInfo(
                    id=gen_id,
                    name=config.get("name", gen_id),
                    description=config.get("description", ""),
                    path=config_file,
                    enabled=config.get("enabled", True),
                    default=config.get("default", False),
                )
                self._generators[gen_id] = info
            except Exception:
                continue

    def list_generators(self) -> List[Dict[str, Any]]:
        """列出所有可用的生成器"""
        return [
            {
                "id": gen.id,
                "name": gen.name,
                "description": gen.description,
                "enabled": gen.enabled,
                "default": gen.default,
            }
            for gen in self._generators.values()
            if gen.enabled
        ]

    def get_default_generator(self) -> Optional[str]:
        """获取默认生成器ID"""
        for gen in self._generators.values():
            if gen.default and gen.enabled:
                return gen.id
        return None

    def get_generator(self, generator_id: str) -> Optional[Dict]:
        """获取生成器配置"""
        if generator_id in self._configs:
            return self._configs[generator_id]

        info = self._generators.get(generator_id)
        if not info or not info.path.exists():
            return None

        with open(info.path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self._configs[generator_id] = config
        return config

    def get_template_path(self, generator_id: str) -> Optional[Path]:
        """获取生成器模板路径"""
        config = self.get_generator(generator_id)
        if not config:
            return None

        template_rel = config.get("template", "")
        if not template_rel:
            return None

        template_path = self.base_path / generator_id / template_rel
        resolved = template_path.resolve()
        return resolved if resolved.exists() else None

    def get_export_template_path(self, generator_id: str) -> Optional[Path]:
        """获取生成器导出模板路径"""
        config = self.get_generator(generator_id)
        if not config:
            return None

        template_rel = config.get("export_template", "")
        if not template_rel:
            return None

        template_path = self.base_path / generator_id / template_rel
        resolved = template_path.resolve()
        return resolved if resolved.exists() else None

    def get_rwkv_template_path(self, generator_id: str) -> Optional[Path]:
        """获取生成器 RWKV 导出模板路径"""
        template_path = self.base_path / generator_id / "templates" / "rwkv.j2"
        resolved = template_path.resolve()
        return resolved if resolved.exists() else None

    def get_tools(self, generator_id: str) -> List[ToolDefinition]:
        """获取生成器的工具列表"""
        config = self.get_generator(generator_id)
        if not config:
            return []

        tools_config = config.get("tools")
        if not isinstance(tools_config, dict):
            return []
        
        # 检查是否有 source 指向外部文件
        source = tools_config.get("source", "")
        if source:
            # 从外部文件加载技能
            skills_path = self.base_path.parent / source
            if skills_path.exists():
                try:
                    import json
                    with open(skills_path, "r", encoding="utf-8") as f:
                        skills_data = json.load(f)
                    
                    tools = []
                    for skill in skills_data.get("skills", []):
                        tools.append(ToolDefinition(
                            name=skill.get("name", ""),
                            alias=skill.get("alias", ""),
                            description=skill.get("description", ""),
                            parameters=skill.get("parameters", {}),
                            risk=skill.get("risk", "low"),
                            help=skill.get("help", ""),
                        ))
                    return tools
                except Exception as e:
                    print(f"Failed to load skills from {source}: {e}")
        
        # 兼容内联配置
        tools = []
        for tool_data in tools_config if isinstance(tools_config, list) else []:
            tools.append(
                ToolDefinition(
                    name=tool_data["name"],
                    description=tool_data["description"],
                    alias=tool_data.get("alias", ""),
                    parameters=tool_data.get("parameters", []),
                    risk=tool_data.get("risk", "low"),
                )
            )
        return tools

    def get_parameters(self, generator_id: str) -> Dict[str, Any]:
        """获取生成器的参数配置"""
        config = self.get_generator(generator_id)
        if not config:
            return {}
        return config.get("parameters", {})

    def get_tts_config(self, generator_id: str) -> Dict[str, Any]:
        """获取生成器的 TTS 配置"""
        config = self.get_generator(generator_id)
        if not config:
            return {"enabled": False}
        return config.get("tts", {"enabled": False})

    def get_output_format(self, generator_id: str) -> Dict[str, Any]:
        """获取生成器的输出格式配置"""
        config = self.get_generator(generator_id)
        if not config:
            return {"schema": "[]", "notes": []}
        return config.get("output_format", {"schema": "[]", "notes": []})

    def get_user_profile_config(self, generator_id: str) -> Dict[str, Any]:
        """获取生成器的用户画像配置"""
        config = self.get_generator(generator_id)
        if not config:
            return {"enabled": False, "fields": []}
        user_profile = config.get("user_profile", {})
        return {
            "enabled": user_profile.get("enabled", False),
            "random_known_fields": user_profile.get("random_known_fields", False),
            "fields": user_profile.get("fields", []),
        }

    def get_system_config(self, generator_id: str) -> Dict[str, Any]:
        """获取生成器的系统配置"""
        config = self.get_generator(generator_id)
        if not config:
            return {"birthday": False, "time_context": False}
        system = config.get("system", {})
        return {
            "birthday": system.get("birthday", False),
            "time_context": system.get("time_context", False),
        }

    def get_topic_config(self, generator_id: str) -> Dict[str, Any]:
        """获取生成器的话题配置"""
        config = self.get_generator(generator_id)
        if not config:
            return {"enabled": False, "source": "", "levels": []}
        topic = config.get("topic", {})
        return {
            "enabled": topic.get("enabled", False),
            "source": topic.get("source", ""),
            "levels": topic.get("levels", []),
        }


_loader: Optional[GeneratorLoader] = None


def get_generator_loader() -> GeneratorLoader:
    """获取全局生成器加载器实例"""
    global _loader
    if _loader is None:
        _loader = GeneratorLoader()
    return _loader


def reload_generator_loader():
    """重新加载生成器配置"""
    global _loader
    _loader = GeneratorLoader()


def list_available_generators() -> List[Dict[str, Any]]:
    """列出所有可用的生成器"""
    return get_generator_loader().list_generators()


def get_generator_config(generator_id: str) -> Optional[Dict]:
    """获取生成器配置"""
    return get_generator_loader().get_generator(generator_id)
