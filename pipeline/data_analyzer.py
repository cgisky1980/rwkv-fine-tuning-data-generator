"""V4 Data Statistics Analyzer

Analyzes generated data for distribution visualization.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any, Optional


class DataAnalyzer:
    """Analyzes data distribution from task files"""

    @staticmethod
    def analyze_task_file(file_path: Path) -> Dict[str, Any]:
        """Analyze a single task file"""
        if not file_path.exists():
            return {}

        stats = {
            "total_records": 0,
            "languages": Counter(),
            "topics": Counter(),
            "personas": Counter(),
            "races": Counter(),
            "tts_instructions": Counter(),
            "tool_usage": Counter(),
            "conversation_lengths": [],
        }

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                    stats["total_records"] += 1

                    lang = record.get("language", "unknown")
                    stats["languages"][lang] += 1

                    topic = record.get("topic", "unknown")
                    if isinstance(topic, dict):
                        topic = topic.get("topic", "unknown")
                    stats["topics"][topic] += 1

                    persona = record.get("system", {}).get("persona", {})
                    if isinstance(persona, dict):
                        tone = persona.get("tone", "unknown")
                        stats["personas"][tone] += 1
                        race = persona.get("race", "unknown")
                        stats["races"][race] += 1

                    if "turns" in record:
                        turns = record.get("turns", [])
                        stats["conversation_lengths"].append(len(turns))

                    elif "user" in record and "assistant" in record:
                        tools = record.get("user", {}).get("tools_usage", [])
                        for tool in tools:
                            tool_name = tool.get("name", "unknown")
                            stats["tool_usage"][tool_name] += 1

                        meta = record.get("meta", {})
                        if meta.get("force_refusal"):
                            stats["tool_usage"]["force_refusal"] += 1

                except json.JSONDecodeError:
                    continue

        return {
            "total_records": stats["total_records"],
            "languages": dict(stats["languages"].most_common(10)),
            "topics": dict(stats["topics"].most_common(10)),
            "personas": dict(stats["personas"].most_common(10)),
            "races": dict(stats["races"].most_common(10)),
            "tool_usage": dict(stats["tool_usage"].most_common(10)),
            "avg_conversation_length": sum(stats["conversation_lengths"])
            / len(stats["conversation_lengths"])
            if stats["conversation_lengths"]
            else 0,
        }

    @staticmethod
    def analyze_multiple_files(file_paths: List[Path]) -> Dict[str, Any]:
        """Analyze multiple task files and aggregate statistics"""
        aggregated = {
            "total_records": 0,
            "total_files": 0,
            "languages": Counter(),
            "topics": Counter(),
            "personas": Counter(),
            "races": Counter(),
            "tool_usage": Counter(),
        }

        for file_path in file_paths:
            file_stats = DataAnalyzer.analyze_task_file(file_path)

            aggregated["total_files"] += 1
            aggregated["total_records"] += file_stats.get("total_records", 0)

            for key in ["languages", "topics", "personas", "races", "tool_usage"]:
                if key in file_stats:
                    for item, count in file_stats[key].items():
                        aggregated[key][item] += count

        return {
            "total_records": aggregated["total_records"],
            "total_files": aggregated["total_files"],
            "languages": dict(aggregated["languages"].most_common(20)),
            "topics": dict(aggregated["topics"].most_common(20)),
            "personas": dict(aggregated["personas"].most_common(20)),
            "races": dict(aggregated["races"].most_common(20)),
            "tool_usage": dict(aggregated["tool_usage"].most_common(20)),
        }

    @staticmethod
    def get_distribution_chart_data(stats: Dict[str, Any]) -> Dict[str, Any]:
        """Convert statistics to chart-friendly format"""
        charts = {}

        lang_names = {
            "zh": "中文", "en": "英文", "ja": "日文", "ko": "韩文",
            "de": "德文", "fr": "法文", "es": "西班牙", "ru": "俄文"
        }

        for key in ["languages", "topics", "personas", "races", "tool_usage"]:
            if key in stats and stats[key]:
                data = stats[key]
                labels = list(data.keys())
                if key == "languages":
                    labels = [lang_names.get(l, l) for l in labels]
                charts[key] = {
                    "labels": labels,
                    "values": list(data.values()),
                    "type": "pie" if len(data) <= 10 else "bar",
                }

        return charts
