# -*- coding: utf-8 -*-
"""
check_lab_reagent_env.py

用于 Windows 本地开发环境检查：
1. 检查 Python / pip / Node.js / npm / Git / VS Code / Docker / 微信开发者工具是否可用
2. 检查后端 Python 依赖是否已安装
3. 检查前端 Node 全局工具是否已安装
4. 生成一份 environment_check_report.txt 报告

使用方法：
    python check_lab_reagent_env.py

说明：
    本脚本只检查“是否已安装/是否能被命令行识别”，不会替你安装软件。
"""

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REPORT_FILE = "environment_check_report.txt"


# 你的项目建议使用的 Python 包
PYTHON_PACKAGES = {
    # Web API 后端
    "fastapi": "FastAPI 后端框架",
    "uvicorn": "FastAPI ASGI 运行器",
    "pydantic": "数据校验",
    "pydantic_settings": "配置管理",
    "sqlalchemy": "数据库 ORM",
    "alembic": "数据库迁移",
    "python_dotenv": "读取 .env 环境变量",

    # 数据处理与报表
    "pandas": "统计分析与报表生成",
    "openpyxl": "Excel 读写",
    "matplotlib": "本地生成图表，可选",

    # 网络请求与定时任务
    "requests": "调用腾讯文档 API / 企业微信机器人",
    "httpx": "异步 HTTP 请求，可选",
    "apscheduler": "定时同步和定时报表",

    # 登录鉴权与安全
    "passlib": "密码哈希，可选",
    "jose": "JWT 令牌，通常来自 python-jose",
    "bcrypt": "密码哈希后端，可选",

    # 测试
    "pytest": "后端单元测试",
}

# 命令行工具检查
COMMANDS = {
    "python": "Python 解释器",
    "pip": "Python 包管理器",
    "node": "Node.js 运行环境",
    "npm": "Node.js 包管理器",
    "npx": "Node.js 临时执行工具",
    "git": "Git 版本管理",
    "code": "VS Code 命令行工具",
    "docker": "Docker，可选，用于后期容器部署",
    "docker-compose": "Docker Compose，可选",
    "pnpm": "pnpm，可选，前端包管理器",
    "yarn": "yarn，可选，前端包管理器",
}

# 可能需要的 Node 全局包
NODE_GLOBAL_PACKAGES = {
    "@tarojs/cli": "Taro 小程序多端开发 CLI，建议安装",
    "typescript": "TypeScript 编译器，建议安装",
}


def run_cmd(cmd: List[str], timeout: int = 8) -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, "command not found"
    except subprocess.TimeoutExpired:
        return False, "command timeout"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def command_version(command: str) -> Tuple[bool, str, Optional[str]]:
    path = shutil.which(command)
    if not path:
        return False, "", None

    version_args = {
        "python": ["python", "--version"],
        "pip": ["pip", "--version"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "npx": ["npx", "--version"],
        "git": ["git", "--version"],
        "code": ["code", "--version"],
        "docker": ["docker", "--version"],
        "docker-compose": ["docker-compose", "--version"],
        "pnpm": ["pnpm", "--version"],
        "yarn": ["yarn", "--version"],
    }.get(command, [command, "--version"])

    ok, out = run_cmd(version_args)
    return ok, out.splitlines()[0] if out else "", path


def check_python_package(import_name: str) -> Tuple[bool, Optional[str]]:
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        return False, None

    # 尝试读取版本号
    try:
        if import_name == "jose":
            module_name = "python-jose"
        elif import_name == "python_dotenv":
            module_name = "python-dotenv"
        else:
            module_name = import_name

        import importlib.metadata as metadata
        version = metadata.version(module_name)
    except Exception:
        version = "installed"

    return True, version


def check_node_global_package(pkg_name: str) -> Tuple[bool, str]:
    npm = shutil.which("npm")
    if not npm:
        return False, "npm not found"

    ok, out = run_cmd(["npm", "list", "-g", pkg_name, "--depth=0"], timeout=15)
    if ok and pkg_name.lower() in out.lower():
        return True, out.splitlines()[-1] if out else "installed"

    return False, "not installed globally"


def detect_wechat_devtools() -> Tuple[bool, List[str]]:
    candidates = [
        r"C:\Program Files (x86)\Tencent\微信web开发者工具",
        r"C:\Program Files\Tencent\微信web开发者工具",
        r"C:\Program Files (x86)\Tencent\微信开发者工具",
        r"C:\Program Files\Tencent\微信开发者工具",
        r"C:\Program Files (x86)\Tencent\WeChat DevTools",
        r"C:\Program Files\Tencent\WeChat DevTools",
    ]

    found = []
    for p in candidates:
        if Path(p).exists():
            found.append(p)

    # 尝试查找 cli.bat
    common_cli = [
        r"C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat",
        r"C:\Program Files\Tencent\微信web开发者工具\cli.bat",
        r"C:\Program Files (x86)\Tencent\微信开发者工具\cli.bat",
        r"C:\Program Files\Tencent\微信开发者工具\cli.bat",
    ]
    for cli in common_cli:
        if Path(cli).exists():
            found.append(cli)

    return len(found) > 0, sorted(set(found))


def recommended_install_commands() -> str:
    return r"""
建议安装命令：

1. Python 后端依赖：
    pip install fastapi uvicorn sqlalchemy alembic pydantic pydantic-settings python-dotenv requests httpx apscheduler pandas openpyxl matplotlib passlib bcrypt python-jose pytest

2. Node / 小程序前端依赖：
    npm install -g typescript @tarojs/cli

3. 若使用 pnpm：
    npm install -g pnpm

4. 若 code 命令不可用：
    打开 VS Code → Ctrl+Shift+P → 输入 Shell Command → 选择 Install 'code' command in PATH
    Windows 上也可以在安装 VS Code 时勾选“添加到 PATH”。

5. 微信开发者工具：
    需要单独安装，安装后建议开启服务端口：
    微信开发者工具 → 设置 → 安全设置 → 服务端口 → 开启
"""


def main() -> None:
    lines: List[str] = []

    lines.append("=" * 80)
    lines.append("实验室试剂仓库管理系统：本地开发环境检查报告")
    lines.append("=" * 80)
    lines.append("")

    lines.append("[系统信息]")
    lines.append(f"OS: {platform.platform()}")
    lines.append(f"Machine: {platform.machine()}")
    lines.append(f"Python executable: {sys.executable}")
    lines.append(f"Current directory: {os.getcwd()}")
    lines.append("")

    lines.append("[命令行工具检查]")
    command_results: Dict[str, bool] = {}
    for cmd, desc in COMMANDS.items():
        ok, version, path = command_version(cmd)
        command_results[cmd] = ok
        mark = "OK" if ok else "MISSING"
        lines.append(f"{mark:8} {cmd:15} {desc}")
        if ok:
            lines.append(f"         version/path: {version} | {path}")
    lines.append("")

    lines.append("[微信开发者工具检查]")
    wx_ok, wx_paths = detect_wechat_devtools()
    if wx_ok:
        lines.append("OK       微信开发者工具疑似已安装：")
        for p in wx_paths:
            lines.append(f"         {p}")
    else:
        lines.append("MISSING  未在常见路径检测到微信开发者工具。若已安装但路径不同，可以忽略。")
    lines.append("")

    lines.append("[Python 包检查]")
    py_missing = []
    for import_name, desc in PYTHON_PACKAGES.items():
        ok, version = check_python_package(import_name)
        mark = "OK" if ok else "MISSING"
        lines.append(f"{mark:8} {import_name:20} {desc} {f'({version})' if version else ''}")
        if not ok:
            py_missing.append(import_name)
    lines.append("")

    lines.append("[Node 全局包检查]")
    node_missing = []
    for pkg, desc in NODE_GLOBAL_PACKAGES.items():
        ok, info = check_node_global_package(pkg)
        mark = "OK" if ok else "MISSING"
        lines.append(f"{mark:8} {pkg:20} {desc} | {info}")
        if not ok:
            node_missing.append(pkg)
    lines.append("")

    lines.append("[结论]")
    required_ok = (
        command_results.get("python", False)
        and command_results.get("pip", False)
        and command_results.get("node", False)
        and command_results.get("npm", False)
        and command_results.get("git", False)
    )

    if required_ok and not py_missing:
        lines.append("核心后端开发环境基本可用。")
    else:
        lines.append("核心环境仍有缺失，请根据下方建议安装。")

    if py_missing:
        lines.append("")
        lines.append("缺失 Python 包：")
        lines.append("    " + " ".join(py_missing))

    if node_missing:
        lines.append("")
        lines.append("缺失 Node 全局包：")
        lines.append("    " + " ".join(node_missing))

    lines.append(recommended_install_commands())

    report = "\n".join(lines)
    print(report)

    Path(REPORT_FILE).write_text(report, encoding="utf-8")
    print(f"\n报告已保存到：{Path(REPORT_FILE).resolve()}")


if __name__ == "__main__":
    main()
