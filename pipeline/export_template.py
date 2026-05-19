import json
import random
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.generators import get_generator_loader


def _fix_trailing_newline(text: str) -> str:
    """Fix trailing newlines: replace \n or \n\n at the end with \n\n# User\n

    This ensures proper formatting for RWKV training where each
    conversation segment ends with a prompt for the next user input.
    """
    target = "\n\n# User\n\n"
    
    # If already has complete marker, return as is
    if text.endswith(target):
        return text
    
    # Check if ends with # User (with optional trailing newlines)
    # and replace appropriately
    if text.endswith('\n\n# User\n'):
        # Has \n\n# User\n, just add \n to complete
        return text + '\n'
    elif text.endswith('\n\n# User'):
        # Has \n\n# User, add \n\n to complete
        return text + '\n\n'
    elif text.endswith('# User'):
        # Has # User, add \n\n# User\n\n
        return text + '\n\n# User\n\n'
    elif text.endswith('\n# User'):
        # Has \n# User, add \n# User\n\n
        return text + '# User\n\n'
    elif text.endswith('# Use') or text.endswith('# U'):
        # Partial # User, remove and replace
        idx = text.rfind('#')
        if idx > 0:
            base = text[:idx]
            if base.endswith('\n'):
                base = base[:-1]
            return base + target
        return text + target
    # No # User at all - handle trailing newlines
    elif text.endswith('\n\n'):
        return text + '# User\n\n'
    elif text.endswith('\n'):
        return text[:-1] + target
    else:
        return text + target


def render_persona_md(persona: dict) -> str:
    """将 persona 渲染为 MD 列表格式"""
    lines = []
    keys = ['name', 'language', 'gender', 'race', 'personality', 'tone', 'user_title']
    for key in keys:
        val = persona.get(key)
        if val:
            lines.append(f"- {key}: {val}")
    
    tics = persona.get('optional_tics', [])
    if isinstance(tics, dict):
        lang = persona.get('language', 'zh')
        tics = tics.get(lang, tics.get('zh', []))
    if tics and isinstance(tics, list):
        lines.append(f"- optional_tics: {', '.join(tics)}")
    
    for key in ['allowed_emotions', 'allowed_actions']:
        val = persona.get(key, [])
        if val and isinstance(val, list):
            lines.append(f"- {key}: {', '.join(val)}")
    
    return '\n'.join(lines)


def get_generator_type(data: dict) -> str:
    """获取数据的生成器类型"""
    generator_type = data.get("generator_type")
    if generator_type:
        return generator_type
    
    turns = data.get("turns", [])
    if isinstance(turns, dict):
        if any(k in turns for k in ["chat_first_case", "tool_first_case", "interleaved_case"]):
            return "mixed_dialog"
    
    if any(k in data for k in ["clarify_then_success", "clarify_then_error", "no_clarify_needed"]):
        return "clarify_skill"

    if any(k in data for k in ["multi_step_case", "orchestration_case", "parallel_case"]):
        return "complex_skill"
    
    if any(k in data for k in ["success_case", "error_case", "cancelled_case"]):
        return "single_skill"
    
    # 根据 skill_output 的 status 判断类型
    turns = data.get("turns", [])
    if turns and len(turns) > 0:
        first_turn = turns[0]
        if isinstance(first_turn, dict):
            skill_calls = first_turn.get("skill_calls", [])
            if skill_calls:
                for sc in skill_calls:
                    skill_output = sc.get("skill_output", {})
                    status = skill_output.get("status", "")
                    if status == "error":
                        return "single_skill_error"
    
    if any(k in data for k in ["chat_first_case", "tool_first_case", "interleaved_case"]):
        return "mixed_dialog"
    
    return "no_tool"


def convert_to_template_format(data: dict, generator_type: str) -> dict:
    """转换数据格式以匹配模板期望的字段名
    
    统一格式：
    {
        "dialogue": [
            {"role": "user", "say": "...", "type": "chat/tool", "skills_usage": [...]},
            {"role": "assistant", "respond": "...", "thought": [...], "skill_calls": [...]}
        ]
    }
    """
    converted = data.copy()
    
    if generator_type in ["single_skill", "single_skill_error", "complex_skill", "clarify_skill"]:
        turns = converted.get("turns", [])
        if turns and len(turns) > 0:
            first_turn = turns[0]
            if isinstance(first_turn, dict):
                user = {}
                assistant = {}
                
                if "user_query" in first_turn:
                    user["say"] = first_turn["user_query"]
                    user["role"] = "user"
                    user["type"] = "tool" if "skill_calls" in first_turn else "chat"
                if "refs" in first_turn:
                    user["refs"] = first_turn["refs"]
                if "time" in first_turn:
                    user["time"] = first_turn["time"]
                if "skills_usage" in first_turn:
                    user["skills_usage"] = first_turn["skills_usage"]
                
                if "thought" in first_turn:
                    assistant["thought"] = first_turn["thought"]
                if "skill_calls" in first_turn:
                    assistant["skill_calls"] = first_turn["skill_calls"]
                if "respond" in first_turn:
                    assistant["respond"] = first_turn["respond"]
                assistant["role"] = "assistant"
                
                converted["dialogue"] = [user, assistant]
                del converted["turns"]
    
    return converted


def export_data(input_file: str, output_file: str = None):
    """导出数据到指定格式"""
    loader = get_generator_loader()
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        data = json.loads(line)
        
        if isinstance(data, list):
            data = data[0] if data else {}
        
        data = _process_turn_times(data)
        
        if "turns" in data and isinstance(data["turns"], list) and len(data["turns"]) > 0:
            first_turn = data["turns"][0]
            if isinstance(first_turn, dict):
                if "conversation" in first_turn:
                    data["turns"] = first_turn["conversation"]
                    conv_times = data.pop("_conversation_turn_times", None)
                    if conv_times:
                        data["_turn_times"] = conv_times
                elif "dialogue" in first_turn:
                    data["turns"] = first_turn["dialogue"]
                elif "role" in first_turn:
                    pass
        
        generator_type = get_generator_type(data)
        
        export_path = loader.get_export_template_path(generator_type)
        if not export_path:
            print(f"Warning: No export template for {generator_type}")
            results.append(json.dumps(data, ensure_ascii=False))
            continue
        
        env = Environment(loader=FileSystemLoader(str(export_path.parent)))
        env.globals['enumerate'] = enumerate
        template = env.get_template(export_path.name)
        rendered = template.render(data)
        results.append(rendered)
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n---\n\n'.join(results))
        print(f"Exported to {output_file}")
    else:
        print('\n---\n\n'.join(results))


def export_rwkv_data(input_file: str, output_file: str = None):
    """导出数据到 RWKV JSONL 格式"""
    loader = get_generator_loader()
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        data = json.loads(line)
        
        if isinstance(data, list):
            data = data[0] if data else {}
        
        data = _process_turn_times(data)
        
        if "turns" in data and isinstance(data["turns"], list) and len(data["turns"]) > 0:
            first_turn = data["turns"][0]
            if isinstance(first_turn, dict):
                if "conversation" in first_turn:
                    data["turns"] = first_turn["conversation"]
                    conv_times = data.pop("_conversation_turn_times", None)
                    if conv_times:
                        data["_turn_times"] = conv_times
                elif "dialogue" in first_turn:
                    data["turns"] = first_turn["dialogue"]
        
        generator_type = get_generator_type(data)
        
        # 转换数据格式以匹配模板
        data = convert_to_template_format(data, generator_type)
        
        rwkv_path = loader.get_rwkv_template_path(generator_type)
        if not rwkv_path:
            print(f"Warning: No RWKV template for {generator_type}")
            continue
        
        env = Environment(loader=FileSystemLoader(str(rwkv_path.parent)))
        env.globals['enumerate'] = enumerate
        env.globals['_render_persona'] = render_persona_md
        
        def safe_tojson(obj):
            from jinja2 import Undefined
            if isinstance(obj, Undefined):
                return 'null'
            return json.dumps(obj, ensure_ascii=False, indent=2)
        
        env.filters['tojson'] = safe_tojson
        template = env.get_template(rwkv_path.name)
        
        def clean_empty_lines(text: str) -> str:
            import re
            lines = text.split('\n')
            result = []
            for line in lines:
                if line.startswith('#'):
                    if result:
                        while result and result[-1].strip() == '':
                            result.pop()
                        result.append('')
                        result.append('')
                    result.append(line)
                else:
                    result.append(line)
            text = '\n'.join(result)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.lstrip('\n')
            return text
        
        if generator_type == 'mixed_dialog':
            cases_data = data.get('turns', [{}])[0] if data.get('turns') else {}
            system_data = data.get('system', {})
            for case_name in ['chat_first_case', 'tool_first_case', 'interleaved_case']:
                case_data = cases_data.get(case_name, {})
                if case_data and case_data.get('dialogue'):
                    dialogue = case_data.get('dialogue', [])
                    time_context = system_data.get('time_context', {})
                    base_datetime = time_context.get('datetime', '')
                    
                    current_time = datetime.now()
                    if base_datetime:
                        try:
                            base_str = base_datetime.replace('/', '-')
                            current_time = datetime.strptime(base_str, "%Y-%m-%d %H:%M")
                        except ValueError:
                            pass
                    
                    is_first = True
                    for idx, turn in enumerate(dialogue):
                        if turn.get('role') == 'user':
                            if 'time' not in turn:
                                if not is_first:
                                    delta_seconds = random.randint(40, 120)
                                    current_time += timedelta(seconds=delta_seconds)
                                turn['time'] = current_time.strftime("%Y/%m/%d %H:%M")
                                is_first = False
                            
                            turn_type = turn.get('type', '')
                            if turn_type == 'tool' or 'skills_usage' not in turn:
                                if idx + 1 < len(dialogue):
                                    next_turn = dialogue[idx + 1]
                                    if next_turn.get('role') == 'assistant' and 'skill_calls' in next_turn:
                                        skill_list = []
                                        for sc in next_turn.get('skill_calls', []):
                                            skill_doc = sc.get('skill_doc', {})
                                            if isinstance(skill_doc, dict):
                                                skill_info = {
                                                    'name': skill_doc.get('name', ''),
                                                    'alias': skill_doc.get('alias', ''),
                                                    'description': skill_doc.get('description', '')
                                                }
                                            else:
                                                skill_info = {
                                                    'name': '',
                                                    'alias': '',
                                                    'description': str(skill_doc) if skill_doc else ''
                                                }
                                            if skill_info['name'] or skill_info['alias']:
                                                skill_list.append(skill_info)
                                        
                                        if skill_list:
                                            all_tools = []
                                            try:
                                                loader = get_generator_loader()
                                                tools = loader.get_tools(generator_type)
                                                for t in tools:
                                                    all_tools.append({
                                                        'name': t.name,
                                                        'alias': t.alias,
                                                        'description': t.description
                                                    })
                                            except:
                                                pass
                                            
                                            used_names = set(s['name'] for s in skill_list)
                                            available = [t for t in all_tools if t['name'] not in used_names]
                                            rng = random.Random(idx * 1000 + len(skill_list))
                                            rng.shuffle(available)
                                            need = max(0, 4 - len(skill_list))
                                            random_skills = available[:need]
                                            
                                            skill_list.extend(random_skills)
                                            rng.shuffle(skill_list)
                                            turn['skills_usage'] = skill_list
                    
                    case_render_data = {
                        'system': system_data,
                        'dialogue': dialogue,
                    }
                    rendered = clean_empty_lines(template.render(case_render_data))
                    rendered = _fix_trailing_newline(rendered)
                    results.append(json.dumps({"text": rendered}, ensure_ascii=False))
        elif generator_type == 'clarify_skill':
            cases_data = data.get('turns', [{}])[0] if data.get('turns') else {}
            system_data = data.get('system', {})
            for case_name in ['clarify_then_success', 'clarify_then_error', 'no_clarify_needed']:
                case_data = cases_data.get(case_name, {})
                if case_data and case_data.get('dialogue'):
                    dialogue = case_data.get('dialogue', [])
                    time_context = system_data.get('time_context', {})
                    base_datetime = time_context.get('datetime', '')

                    current_time = datetime.now()
                    if base_datetime:
                        try:
                            base_str = base_datetime.replace('/', '-')
                            current_time = datetime.strptime(base_str, "%Y-%m-%d %H:%M")
                        except ValueError:
                            pass

                    is_first = True
                    for idx, turn in enumerate(dialogue):
                        if turn.get('role') == 'user':
                            if 'time' not in turn:
                                if not is_first:
                                    delta_seconds = random.randint(40, 120)
                                    current_time += timedelta(seconds=delta_seconds)
                                turn['time'] = current_time.strftime("%Y/%m/%d %H:%M")
                                is_first = False

                            turn_type = turn.get('type', '')
                            if turn_type == 'tool' or turn_type == 'clarify_needed' or 'skills_usage' not in turn:
                                if idx + 1 < len(dialogue):
                                    next_turn = dialogue[idx + 1]
                                    if next_turn.get('role') == 'assistant' and 'skill_calls' in next_turn:
                                        skill_list = []
                                        for sc in next_turn.get('skill_calls', []):
                                            skill_doc = sc.get('skill_doc', {})
                                            if isinstance(skill_doc, dict):
                                                skill_info = {
                                                    'name': skill_doc.get('name', ''),
                                                    'alias': skill_doc.get('alias', ''),
                                                    'description': skill_doc.get('description', '')
                                                }
                                            else:
                                                skill_info = {
                                                    'name': '',
                                                    'alias': '',
                                                    'description': str(skill_doc) if skill_doc else ''
                                                }
                                            if skill_info['name'] or skill_info['alias']:
                                                skill_list.append(skill_info)

                                        if skill_list:
                                            all_tools = []
                                            try:
                                                loader = get_generator_loader()
                                                tools = loader.get_tools(generator_type)
                                                for t in tools:
                                                    all_tools.append({
                                                        'name': t.name,
                                                        'alias': t.alias,
                                                        'description': t.description
                                                    })
                                            except:
                                                pass

                                            used_names = set(s['name'] for s in skill_list)
                                            available = [t for t in all_tools if t['name'] not in used_names]
                                            rng = random.Random(idx * 1000 + len(skill_list))
                                            rng.shuffle(available)
                                            need = max(0, 4 - len(skill_list))
                                            random_skills = available[:need]

                                            skill_list.extend(random_skills)
                                            rng.shuffle(skill_list)
                                            turn['skills_usage'] = skill_list

                    case_render_data = {
                        'system': system_data,
                        'dialogue': dialogue,
                    }
                    rendered = clean_empty_lines(template.render(case_render_data))
                    rendered = _fix_trailing_newline(rendered)
                    results.append(json.dumps({"text": rendered}, ensure_ascii=False))
        else:
            rendered = clean_empty_lines(template.render(data))
            rendered = _fix_trailing_newline(rendered)
            results.append(json.dumps({"text": rendered}, ensure_ascii=False))
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(results))
        print(f"Exported {len(results)} records to {output_file}")
    else:
        print('\n'.join(results))
    
    return len(results)


def _process_turn_times(data: dict) -> dict:
    """处理每轮对话的时间递增"""
    turns = data.get("turns", [])
    
    if turns and isinstance(turns[0], dict) and "conversation" in turns[0]:
        conversation = turns[0].get("conversation", [])
    else:
        conversation = turns
    
    base_time = datetime.now()
    current_time = base_time
    
    time_context = data.get("system", {}).get("time_context", {})
    if time_context:
        base_str = time_context.get("datetime", "")
        try:
            current_time = datetime.strptime(base_str, "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    
    turn_times = []
    is_first = True
    for turn in conversation:
        if turn.get("role") == "user":
            if not is_first:
                delta_seconds = random.randint(40, 120)
                current_time += timedelta(seconds=delta_seconds)
            
            time_str = current_time.strftime("%Y/%m/%d %H:%M")
            turn_times.append(time_str)
            is_first = False
        else:
            turn_times.append(None)
    
    if turns and isinstance(turns[0], dict) and "conversation" in turns[0]:
        data["_conversation_turn_times"] = turn_times
    else:
        data["_turn_times"] = turn_times
    
    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="V4 数据导出工具")
    parser.add_argument("input_file", help="输入 JSONL 文件路径")
    parser.add_argument("-o", "--output", help="输出文件路径")
    parser.add_argument("--rwkv", action="store_true", help="导出为 RWKV JSONL 格式")
    args = parser.parse_args()
    
    if args.rwkv:
        export_rwkv_data(args.input_file, args.output)
    else:
        export_data(args.input_file, args.output)
