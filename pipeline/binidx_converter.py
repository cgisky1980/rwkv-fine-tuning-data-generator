"""V4 Binidx Converter Tool Integration

集成 json2binidx_tool 进行 RWKV 训练数据转换
工具地址: https://github.com/Abel2076/json2binidx_tool

说明:
json2binidx_tool 已整合到 V4/pipeline/json2binidx_tool 目录
用户无需额外安装，开箱即用。
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def get_default_tool_path() -> Path:
    """获取默认工具路径 (已整合到 V4 中)"""
    # 工具已整合在 pipeline/json2binidx_tool
    current_file = Path(__file__).resolve()
    tool_path = current_file.parent / "json2binidx_tool"
    return tool_path


class BinidxConverter:
    """json2binidx_tool 的包装器

    工具已整合到系统中，开箱即用，无需用户安装。
    """

    def __init__(self, tool_path: Optional[Path] = None):
        """初始化转换器

        Args:
            tool_path: json2binidx_tool 目录路径。
                      默认为内置路径 V4/pipeline/json2binidx_tool
        """
        self.tool_path = tool_path or get_default_tool_path()
        self.vocab_file = self.tool_path / "rwkv_vocab_v20230424.txt"
        self.preprocess_script = self.tool_path / "tools/preprocess_data.py"

    def is_installed(self) -> bool:
        """检查 json2binidx 工具是否可用"""
        return (
            self.tool_path.exists()
            and self.preprocess_script.exists()
            and self.vocab_file.exists()
        )

    def convert_jsonl_to_binidx(
        self,
        input_file: Path,
        output_prefix: Path,
        append_eod: bool = True,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """调用 json2binidx_tool 将 JSONL 转换为 binidx 格式

        实际执行的命令:
            python json2binidx_tool/tools/preprocess_data.py \\
                --input <input.jsonl> \\
                --output-prefix <output> \\
                --vocab json2binidx_tool/rwkv_vocab_v20230424.txt \\
                --dataset-impl mmap \\
                --tokenizer-type RWKVTokenizer \\
                --append-eod

        Args:
            input_file: 输入 JSONL 文件路径
            output_prefix: 输出文件前缀 (不含扩展名)
            append_eod: 是否添加文档结束标记
            verbose: 是否打印详细输出

        Returns:
            包含转换结果的字典
        """
        # 检查工具是否可用
        if not self.is_installed():
            return {
                "success": False,
                "error": "json2binidx_tool not found in V4/pipeline/json2binidx_tool",
            }

        # 检查输入文件是否存在
        if not input_file.exists():
            return {
                "success": False,
                "error": f"Input file not found: {input_file}",
            }

        # 确保输出目录存在
        output_prefix.parent.mkdir(parents=True, exist_ok=True)

        # 构建命令
        cmd = [
            sys.executable,
            str(self.preprocess_script),
            "--input",
            str(input_file),
            "--output-prefix",
            str(output_prefix),
            "--vocab",
            str(self.vocab_file),
            "--dataset-impl",
            "mmap",
            "--tokenizer-type",
            "RWKVTokenizer",
        ]

        if append_eod:
            cmd.append("--append-eod")

        if verbose:
            print(f"Converting {input_file} to binidx format...")
            print(f"  Using tool: {self.tool_path}")

        try:
            # 调用外部工具
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 分钟超时
            )

            if result.returncode == 0:
                # 检查输出文件是否创建成功
                bin_file = Path(f"{output_prefix}.bin")
                idx_file = Path(f"{output_prefix}.idx")

                if bin_file.exists() and idx_file.exists():
                    return {
                        "success": True,
                        "bin_file": str(bin_file.absolute()),
                        "idx_file": str(idx_file.absolute()),
                        "bin_size_mb": round(bin_file.stat().st_size / 1024 / 1024, 2),
                        "idx_size_mb": round(idx_file.stat().st_size / 1024 / 1024, 2),
                        "stdout": result.stdout if verbose else None,
                    }
                else:
                    return {
                        "success": False,
                        "error": "Tool executed but output files not found",
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
            else:
                return {
                    "success": False,
                    "error": f"Tool failed with return code {result.returncode}",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Conversion timeout (10 minutes)",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Conversion error: {str(e)}",
            }

    def validate_binidx_files(self, output_prefix: Path) -> Dict[str, Any]:
        """验证 binidx 文件是否正确生成

        Args:
            output_prefix: 输出文件前缀

        Returns:
            验证结果字典
        """
        bin_file = Path(f"{output_prefix}.bin")
        idx_file = Path(f"{output_prefix}.idx")

        results = {
            "valid": True,
            "bin_exists": bin_file.exists(),
            "idx_exists": idx_file.exists(),
            "errors": [],
        }

        if not results["bin_exists"]:
            results["valid"] = False
            results["errors"].append(f"BIN file not found: {bin_file}")

        if not results["idx_exists"]:
            results["valid"] = False
            results["errors"].append(f"IDX file not found: {idx_file}")

        if results["valid"]:
            bin_size = bin_file.stat().st_size
            idx_size = idx_file.stat().st_size

            results["bin_size_mb"] = round(bin_size / 1024 / 1024, 2)
            results["idx_size_mb"] = round(idx_size / 1024 / 1024, 2)

            if bin_size == 0:
                results["valid"] = False
                results["errors"].append("BIN file is empty")

            if idx_size == 0:
                results["valid"] = False
                results["errors"].append("IDX file is empty")

        return results


# 便捷函数：完整的 V4 -> RWKV -> binidx 转换流程
def convert_v4_to_binidx(
    jsonl_file: Path,
    output_prefix: Optional[Path] = None,
    tool_path: Optional[Path] = None,
    format_type: str = "multi_turn",
    shuffle: bool = True,
    repeat_times: int = 1,
    seed: int = 42,
) -> Dict[str, Any]:
    """完整的 V4 到 binidx 转换流程

    此函数执行以下步骤:
    1. 将 V4 格式转换为 RWKV JSONL 格式
    2. 打乱和重复数据
    3. 调用 json2binidx_tool 转换为 binidx

    Args:
        jsonl_file: 输入 V4 JSONL 文件
        output_prefix: 输出前缀
        tool_path: json2binidx 工具路径 (默认使用内置工具)
        format_type: RWKV 格式类型 (single_turn/multi_turn/instruction)
        shuffle: 是否打乱数据
        repeat_times: 重复次数
        seed: 随机种子

    Returns:
        转换结果字典
    """
    from .rwkv_converter import convert_v4_to_rwkv_jsonl

    # 设置默认输出前缀
    if output_prefix is None:
        output_prefix = jsonl_file.parent / f"{jsonl_file.stem}_rwkv"

    # 步骤 1: 转换为 RWKV 格式
    rwkv_jsonl = Path(f"{output_prefix}_formatted.jsonl")

    print(f"Step 1: Converting V4 to RWKV format...")
    num_records = convert_v4_to_rwkv_jsonl(
        jsonl_file,
        rwkv_jsonl,
        format_type=format_type,
        shuffle=shuffle,
        repeat_times=repeat_times,
        seed=seed,
    )
    print(f"  ✓ Converted {num_records} records")

    # 步骤 2: 转换为 binidx (使用内置工具)
    converter = BinidxConverter(tool_path)

    print(f"\nStep 2: Converting to binidx format...")
    result = converter.convert_jsonl_to_binidx(
        rwkv_jsonl, output_prefix, append_eod=True, verbose=True
    )

    if result["success"]:
        print(f"\n✅ Conversion successful!")
        print(f"  BIN: {result['bin_file']} ({result['bin_size_mb']} MB)")
        print(f"  IDX: {result['idx_file']} ({result['idx_size_mb']} MB)")
    else:
        print(f"\n❌ Conversion failed!")
        print(f"  Error: {result.get('error')}")

    return {
        "success": result["success"],
        "rwkv_jsonl": str(rwkv_jsonl.absolute()),
        "num_records": num_records,
        **result,
    }
