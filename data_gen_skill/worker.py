"""
Agent 工作器 — 参考实现

展示 Agent 如何与 GenTaskDispatcher 交互：
  1. 拉取工作项 (pull_work_items)
  2. 用自己的 LLM 生成数据 (generate_for_item)
  3. 提交结果 (submit_result)

真实 Agent（如 SOLO）替换 generate_for_item() 方法即可。
"""

import json
import time
from typing import Any, Dict, List, Optional

from .dispatcher import GenTaskDispatcher


class GenAgentWorker:
    def __init__(self, agent_id: str, dispatcher: GenTaskDispatcher):
        self.agent_id = agent_id
        self.dispatcher = dispatcher
        self._running = False
        self._stats = {"pulled": 0, "submitted": 0, "failed": 0}

    def run_loop(
        self,
        batch_size: int = 3,
        max_iterations: int = 0,
        sleep_empty: float = 5.0,
    ):
        self._running = True
        iteration = 0

        while self._running:
            iteration += 1
            if max_iterations > 0 and iteration > max_iterations:
                break

            items = self.dispatcher.pull_work_items(self.agent_id, batch_size)
            if not items:
                time.sleep(sleep_empty)
                continue

            self._stats["pulled"] += len(items)
            for item_dict in items:
                try:
                    data = self.generate_for_item(item_dict)
                    result = self.dispatcher.submit_result(
                        self.agent_id, item_dict["item_id"], data
                    )
                    if result["success"]:
                        self._stats["submitted"] += 1
                    else:
                        self._stats["failed"] += 1
                except Exception as e:
                    self._stats["failed"] += 1

    def stop(self):
        self._running = False

    def generate_for_item(self, item: dict) -> dict:
        raise NotImplementedError(
            "Agent must implement generate_for_item(). "
            "Use its own LLM to generate data conforming to the generator's schema. "
            "See the mock implementation in MockAgentWorker for reference."
        )

    @property
    def stats(self) -> dict:
        return dict(self._stats)


class MockAgentWorker(GenAgentWorker):
    """Mock Agent — 生成占位数据用于测试"""

    def generate_for_item(self, item: dict) -> dict:
        gen_type = item.get("task_id", "").split("_")[0] if item.get("task_id") else "clarify_skill"

        if "clarify" in gen_type:
            return self._mock_clarify_skill(item)
        elif "single" in gen_type:
            return self._mock_single_skill(item)
        else:
            return self._mock_clarify_skill(item)

    def _mock_clarify_skill(self, item: dict) -> dict:
        lang = item.get("language", "zh")
        topic = item.get("topic", "general")
        skill = item.get("skill", "weather_api")

        if lang == "zh":
            return {
                "clarify_then_success": {
                    "dialogue": [
                        {
                            "role": "user",
                            "say": "帮我查一下天气",
                            "time": "2026/05/20 10:00",
                            "type": "clarify_needed",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User asked to check weather without specifying city",
                                    "reasoning": "Need to clarify which city before calling weather API",
                                    "reflection": "Ask user for city name politely",
                                    "action": "clarify",
                                }
                            ],
                            "respond": "{V:温柔询问的语气,A:歪头} 好的呀~请问您想查哪个城市的天气呢？",
                        },
                        {
                            "role": "user",
                            "say": "北京",
                            "time": "2026/05/20 10:01",
                            "type": "tool",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User specified Beijing",
                                    "reasoning": "Now have complete info to call weather API",
                                    "reflection": "Call weather_api with city=Beijing",
                                    "action": "call_skill",
                                }
                            ],
                            "skill_calls": [
                                {
                                    "step": 1,
                                    "skill_respond": "Checking Beijing weather...",
                                    "skill_doc": {
                                        "name": "weather_api",
                                        "alias": "天象探查术",
                                        "description": "获取指定城市的天气信息",
                                        "parameters": {
                                            "type": "object",
                                            "properties": {
                                                "city": {
                                                    "type": "string",
                                                    "description": "城市名称",
                                                }
                                            },
                                            "required": ["city"],
                                        },
                                        "example": '{"city": "Beijing"}',
                                        "notes": "支持全球主要城市",
                                    },
                                    "skill_call": {
                                        "name": "weather_api",
                                        "arguments": {"city": "北京"},
                                    },
                                    "skill_output": {
                                        "status": "success",
                                        "result": {
                                            "city": "北京",
                                            "temperature": "26°C",
                                            "weather": "晴",
                                            "humidity": "45%",
                                        },
                                    },
                                    "skill_end": [
                                        {
                                            "observation": "Weather API returned Beijing weather: 26°C sunny",
                                            "reasoning": "Present weather info clearly to user",
                                            "reflection": "Add friendly tone per persona",
                                            "action": "respond",
                                        }
                                    ],
                                }
                            ],
                            "respond": "{V:开心明亮的语调,A:微笑} 北京的天气是晴天，温度26°C，湿度45%！天气不错呢~",
                        },
                    ]
                },
                "clarify_then_error": {
                    "dialogue": [
                        {
                            "role": "user",
                            "say": "帮我查一下天气",
                            "time": "2026/05/20 10:00",
                            "type": "clarify_needed",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User asked to check weather without specifying city",
                                    "reasoning": "Need city name to call weather API",
                                    "reflection": "Ask user which city",
                                    "action": "clarify",
                                }
                            ],
                            "respond": "{V:温柔询问的语气,A:歪头} 好的呀~请问您想查哪个城市的天气呢？",
                        },
                        {
                            "role": "user",
                            "say": "北京",
                            "time": "2026/05/20 10:01",
                            "type": "tool",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User specified Beijing",
                                    "reasoning": "Call weather API for Beijing",
                                    "reflection": "Proceed with API call",
                                    "action": "call_skill",
                                }
                            ],
                            "skill_calls": [
                                {
                                    "step": 1,
                                    "skill_respond": "Checking Beijing weather...",
                                    "skill_doc": {
                                        "name": "weather_api",
                                        "alias": "天象探查术",
                                        "description": "获取指定城市的天气信息",
                                        "parameters": {
                                            "type": "object",
                                            "properties": {
                                                "city": {
                                                    "type": "string",
                                                    "description": "城市名称",
                                                }
                                            },
                                            "required": ["city"],
                                        },
                                        "example": '{"city": "Beijing"}',
                                        "notes": "支持全球主要城市",
                                    },
                                    "skill_call": {
                                        "name": "weather_api",
                                        "arguments": {"city": "北京"},
                                    },
                                    "skill_output": {
                                        "status": "error",
                                        "error": {
                                            "code": "SERVICE_UNAVAILABLE",
                                            "message": "Weather service temporarily unavailable",
                                        },
                                    },
                                    "skill_end": [
                                        {
                                            "observation": "Weather API returned error: service unavailable",
                                            "reasoning": "Cannot get weather data now",
                                            "reflection": "Apologize and suggest retry later",
                                            "action": "respond",
                                        }
                                    ],
                                }
                            ],
                            "respond": "{V:抱歉歉意的语气,A:低头} 抱歉，天气服务暂时不可用...请稍后再试哦~",
                        },
                    ]
                },
                "no_clarify_needed": {
                    "dialogue": [
                        {
                            "role": "user",
                            "say": "帮我查一下北京的天气",
                            "time": "2026/05/20 10:00",
                            "type": "tool",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User wants Beijing weather, city is specified",
                                    "reasoning": "All info complete, call weather API directly",
                                    "reflection": "No clarification needed",
                                    "action": "call_skill",
                                }
                            ],
                            "skill_calls": [
                                {
                                    "step": 1,
                                    "skill_respond": "Checking Beijing weather...",
                                    "skill_doc": {
                                        "name": "weather_api",
                                        "alias": "天象探查术",
                                        "description": "获取指定城市的天气信息",
                                        "parameters": {
                                            "type": "object",
                                            "properties": {
                                                "city": {
                                                    "type": "string",
                                                    "description": "城市名称",
                                                }
                                            },
                                            "required": ["city"],
                                        },
                                        "example": '{"city": "Beijing"}',
                                        "notes": "支持全球主要城市",
                                    },
                                    "skill_call": {
                                        "name": "weather_api",
                                        "arguments": {"city": "北京"},
                                    },
                                    "skill_output": {
                                        "status": "success",
                                        "result": {
                                            "city": "北京",
                                            "temperature": "26°C",
                                            "weather": "晴",
                                            "humidity": "45%",
                                        },
                                    },
                                    "skill_end": [
                                        {
                                            "observation": "Beijing weather: 26°C sunny",
                                            "reasoning": "User already specified city, call was direct",
                                            "reflection": "Report weather clearly",
                                            "action": "respond",
                                        }
                                    ],
                                }
                            ],
                            "respond": "{V:开心明亮的语调,A:微笑} 北京的天气是晴天，温度26°C，湿度45%！",
                        },
                    ]
                },
            }
        else:
            return {
                "clarify_then_success": {
                    "dialogue": [
                        {
                            "role": "user",
                            "say": "Check the weather for me",
                            "time": "2026/05/20 10:00",
                            "type": "clarify_needed",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User requested weather without city",
                                    "reasoning": "Need city name",
                                    "reflection": "Ask which city",
                                    "action": "clarify",
                                }
                            ],
                            "respond": "{V:gentle questioning tone,A:tilt head} Sure! Which city would you like me to check?",
                        },
                        {
                            "role": "user",
                            "say": "London",
                            "time": "2026/05/20 10:01",
                            "type": "tool",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User specified London",
                                    "reasoning": "Complete info, call weather API",
                                    "reflection": "Proceed with API call",
                                    "action": "call_skill",
                                }
                            ],
                            "skill_calls": [
                                {
                                    "step": 1,
                                    "skill_respond": "Checking London weather...",
                                    "skill_doc": {
                                        "name": "weather_api",
                                        "alias": "Weather Probe",
                                        "description": "Get weather information for a city",
                                        "parameters": {
                                            "type": "object",
                                            "properties": {
                                                "city": {
                                                    "type": "string",
                                                    "description": "City name",
                                                }
                                            },
                                            "required": ["city"],
                                        },
                                        "example": '{"city": "London"}',
                                        "notes": "Supports major cities worldwide",
                                    },
                                    "skill_call": {
                                        "name": "weather_api",
                                        "arguments": {"city": "London"},
                                    },
                                    "skill_output": {
                                        "status": "success",
                                        "result": {
                                            "city": "London",
                                            "temperature": "18°C",
                                            "weather": "Cloudy",
                                            "humidity": "65%",
                                        },
                                    },
                                    "skill_end": [
                                        {
                                            "observation": "London: 18°C cloudy",
                                            "reasoning": "Report weather clearly",
                                            "reflection": "Use friendly tone",
                                            "action": "respond",
                                        }
                                    ],
                                }
                            ],
                            "respond": "{V:cheerful tone,A:smile} London weather: Cloudy, 18°C, humidity 65%!",
                        },
                    ]
                },
                "clarify_then_error": {
                    "dialogue": [
                        {
                            "role": "user",
                            "say": "Check the weather for me",
                            "time": "2026/05/20 10:00",
                            "type": "clarify_needed",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User wants weather without city",
                                    "reasoning": "Need city to proceed",
                                    "reflection": "Ask which city",
                                    "action": "clarify",
                                }
                            ],
                            "respond": "{V:gentle tone,A:tilt head} Sure! Which city?",
                        },
                        {
                            "role": "user",
                            "say": "London",
                            "time": "2026/05/20 10:01",
                            "type": "tool",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User specified London",
                                    "reasoning": "Call weather API",
                                    "reflection": "Proceed",
                                    "action": "call_skill",
                                }
                            ],
                            "skill_calls": [
                                {
                                    "step": 1,
                                    "skill_respond": "Checking...",
                                    "skill_doc": {
                                        "name": "weather_api",
                                        "alias": "Weather Probe",
                                        "description": "Get weather information",
                                        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
                                        "example": '{"city": "London"}',
                                        "notes": "",
                                    },
                                    "skill_call": {"name": "weather_api", "arguments": {"city": "London"}},
                                    "skill_output": {"status": "error", "error": {"code": "TIMEOUT", "message": "Request timed out"}},
                                    "skill_end": [{"observation": "API timeout", "reasoning": "Cannot get data", "reflection": "Apologize", "action": "respond"}],
                                }
                            ],
                            "respond": "{V:apologetic tone} Sorry, the weather service timed out. Please try again later.",
                        },
                    ]
                },
                "no_clarify_needed": {
                    "dialogue": [
                        {
                            "role": "user",
                            "say": "What's the weather in London?",
                            "time": "2026/05/20 10:00",
                            "type": "tool",
                        },
                        {
                            "role": "assistant",
                            "thought": [
                                {
                                    "observation": "User wants London weather, city specified",
                                    "reasoning": "Complete info, call directly",
                                    "reflection": "No clarification needed",
                                    "action": "call_skill",
                                }
                            ],
                            "skill_calls": [
                                {
                                    "step": 1,
                                    "skill_respond": "Checking...",
                                    "skill_doc": {"name": "weather_api", "alias": "Weather Probe", "description": "Get weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}, "example": '{"city": "London"}', "notes": ""},
                                    "skill_call": {"name": "weather_api", "arguments": {"city": "London"}},
                                    "skill_output": {"status": "success", "result": {"city": "London", "temperature": "18°C", "weather": "Cloudy"}},
                                    "skill_end": [{"observation": "London: 18°C cloudy", "reasoning": "Report", "reflection": "", "action": "respond"}],
                                }
                            ],
                            "respond": "{V:cheerful tone,A:smile} London: Cloudy, 18°C!",
                        },
                    ]
                },
            }

    def _mock_single_skill(self, item: dict) -> dict:
        lang = item.get("language", "zh")
        if lang == "zh":
            return {
                "success_case": {
                    "dialogue": [
                        {"role": "user", "say": "读取 /home/test.txt 文件", "time": "2026/05/20 10:00", "type": "tool"},
                        {
                            "role": "assistant",
                            "thought": [{"observation": "User wants to read a file", "reasoning": "File path is complete", "reflection": "Call read_file", "action": "call_skill"}],
                            "skill_calls": [{
                                "step": 1,
                                "skill_respond": "Reading file...",
                                "skill_doc": {"name": "read_file", "description": "Read file content", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, "example": '{"path": "/home/test.txt"}', "notes": ""},
                                "skill_call": {"name": "read_file", "arguments": {"path": "/home/test.txt"}},
                                "skill_output": {"status": "success", "result": {"content": "Hello World"}},
                                "skill_end": [{"observation": "File read successfully", "reasoning": "Report content", "reflection": "", "action": "respond"}],
                            }],
                            "respond": "{V:平静的语调} 文件内容是：Hello World",
                        },
                    ]
                },
                "error_case": {
                    "dialogue": [
                        {"role": "user", "say": "读取 /home/nonexistent.txt", "time": "2026/05/20 10:01", "type": "tool"},
                        {
                            "role": "assistant",
                            "thought": [{"observation": "User wants to read a file", "reasoning": "Path exists but file may not", "reflection": "Call read_file", "action": "call_skill"}],
                            "skill_calls": [{
                                "step": 1,
                                "skill_respond": "Checking file...",
                                "skill_doc": {"name": "read_file", "description": "Read file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, "example": '{"path": "/home/test.txt"}', "notes": ""},
                                "skill_call": {"name": "read_file", "arguments": {"path": "/home/nonexistent.txt"}},
                                "skill_output": {"status": "error", "error": {"code": "FILE_NOT_FOUND", "message": "File does not exist"}},
                                "skill_end": [{"observation": "File not found", "reasoning": "Report error", "reflection": "", "action": "respond"}],
                            }],
                            "respond": "{V:抱歉的语气} 文件不存在呢，请检查路径是否正确~",
                        },
                    ]
                },
            }
        return {
            "success_case": {
                "dialogue": [
                    {"role": "user", "say": "Read /home/test.txt", "time": "2026/05/20 10:00", "type": "tool"},
                    {
                        "role": "assistant",
                        "thought": [{"observation": "Read file request", "reasoning": "Complete info", "reflection": "", "action": "call_skill"}],
                        "skill_calls": [{"step": 1, "skill_respond": "Reading...", "skill_doc": {"name": "read_file", "description": "Read file", "parameters": {}, "example": "", "notes": ""}, "skill_call": {"name": "read_file", "arguments": {"path": "/home/test.txt"}}, "skill_output": {"status": "success", "result": {"content": "Hello"}}, "skill_end": [{"observation": "Done", "reasoning": "Report", "reflection": "", "action": "respond"}]}],
                        "respond": "{V:calm tone} File content: Hello",
                    },
                ]
            }
        }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from .dispatcher import get_dispatcher

    d = get_dispatcher()
    worker = MockAgentWorker("test_agent", d)
    print(f"MockAgentWorker ready: {worker.agent_id}")
    print(f"  generate_for_item() will produce mock data for testing")