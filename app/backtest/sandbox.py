"""安全沙箱 - 在子进程中执行用户策略代码"""
import ast
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile

import pandas as pd

logger = logging.getLogger(__name__)

# import 白名单
ALLOWED_IMPORTS = {
    'pandas', 'pd', 'numpy', 'np', 'math', 'statistics',
    'collections', 'itertools', 'functools', 'decimal',
}

# 危险函数调用黑名单
BLOCKED_CALLS = {
    'exec', 'eval', 'open', '__import__', 'compile',
    'globals', 'locals', 'getattr', 'setattr',
}


def check_code_safety(code: str) -> tuple:
    """AST 静态安全检查

    Returns:
        (is_safe: bool, error_message: str)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"语法错误: {e}"

    has_strategy_func = False

    for node in ast.walk(tree):
        # 检查 import 语句
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split('.')[0]
                if module not in ALLOWED_IMPORTS:
                    return False, f"禁止导入模块: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split('.')[0]
                if module not in ALLOWED_IMPORTS:
                    return False, f"禁止导入模块: {node.module}"
        # 检查危险函数调用
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                return False, f"禁止调用函数: {node.func.id}"
        # 检查是否包含 strategy 函数定义
        elif isinstance(node, ast.FunctionDef) and node.name == 'strategy':
            has_strategy_func = True

    if not has_strategy_func:
        return False, "代码中必须包含 def strategy(data): 函数"

    return True, ""


def run_user_strategy(code: str, df: pd.DataFrame, timeout: int = 30) -> dict:
    """在子进程中安全执行用户策略代码

    Args:
        code: 用户 Python 策略代码
        df: 历史数据 DataFrame
        timeout: 超时秒数

    Returns:
        {"success": True, "signals": [...]}
        {"success": False, "error": "..."}
    """
    # 1. AST 安全检查
    is_safe, error_msg = check_code_safety(code)
    if not is_safe:
        return {"success": False, "error": error_msg}

    # 2. 保存数据到临时 CSV
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False, encoding='utf-8'
    )
    try:
        df.to_csv(tmp.name, index=False)
        tmp.close()

        # 3. 构造子进程 wrapper 代码
        wrapper_code = _build_wrapper(code, tmp.name)

        # 4. 构造安全的环境变量（最小化）
        safe_env = {
            'PATH': os.environ.get('PATH', ''),
            'SYSTEMROOT': os.environ.get('SYSTEMROOT', ''),  # Windows 需要
            'TEMP': os.environ.get('TEMP', ''),
            'TMP': os.environ.get('TMP', ''),
        }
        # Linux 下添加 HOME
        if platform.system() != 'Windows':
            safe_env['HOME'] = os.environ.get('HOME', '/tmp')

        # 5. 在子进程中执行
        python_exe = sys.executable
        result = subprocess.run(
            [python_exe, '-c', wrapper_code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=safe_env,
        )

        if result.returncode != 0:
            error = result.stderr.strip()
            if not error:
                error = "策略执行失败（未知错误）"
            return {"success": False, "error": error}

        # 6. 解析 signals
        stdout = result.stdout.strip()
        if not stdout:
            return {"success": False, "error": "策略函数没有返回有效的信号数据"}

        signals = json.loads(stdout)
        if not isinstance(signals, list):
            return {"success": False, "error": "策略返回值格式错误：需要返回 Series/列表"}

        return {"success": True, "signals": signals}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"策略执行超时（{timeout}秒），请检查是否存在死循环"}
    except json.JSONDecodeError:
        return {"success": False, "error": "策略输出解析失败，请确保 strategy() 返回 pandas Series"}
    except Exception as e:
        logger.error(f"Sandbox execution error: {e}")
        return {"success": False, "error": f"沙箱执行异常: {str(e)}"}
    finally:
        # 确保删除临时文件
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _build_wrapper(user_code: str, csv_path: str) -> str:
    """构造子进程执行的 wrapper 代码"""
    # 将路径中的反斜杠转义
    safe_path = csv_path.replace('\\', '\\\\')

    # Linux 下添加内存限制
    resource_limit = ""
    if platform.system() != 'Windows':
        resource_limit = """
import resource
# 限制内存 256MB
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
"""

    wrapper = f"""import sys
import json
import pandas as pd
import numpy as np
import math
{resource_limit}
data = pd.read_csv("{safe_path}")

{user_code}

_signals = strategy(data)

if not hasattr(_signals, 'tolist'):
    print(json.dumps(list(_signals)))
else:
    print(json.dumps(_signals.tolist()))
"""
    return wrapper
