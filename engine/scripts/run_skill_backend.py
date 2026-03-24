#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from resolve_backend import DEFAULT_BACKEND_ENV_VAR, resolve_skill_backend  # noqa: E402


CONFIG_ENV_VAR = "LUCIDE_ICONS_COMPOSE_CONFIG"
PROJECT_CONFIG_CANDIDATES = (
    "lucide-icons-compose.config.json",
    ".codex/lucide-icons-compose.json",
    "config.json",
)


def is_windows() -> bool:
    return os.name == "nt"


def get_python_command() -> list[str]:
    if sys.executable:
        return [sys.executable]
    if is_windows():
        return ["python"]
    return ["python3"]


def get_skill_backend_command(skill_backend_root: Path) -> list[str]:
    return [*get_python_command(), "-m", "engine.cli"]


def get_valkyrie_binary_name() -> str:
    return "valkyrie.bat" if is_windows() else "valkyrie"


def is_valkyrie_runtime_ready(skill_backend_root: Path) -> bool:
    valkyrie_dir = skill_backend_root / "engine" / "valkyrie-cli"
    valkyrie_bin = valkyrie_dir / "bin" / get_valkyrie_binary_name()
    return valkyrie_bin.exists() and (valkyrie_dir / "lib").exists()


def build_skill_backend_env(skill_backend_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = str((skill_backend_root / ".cache" / "pycache").resolve())
    return env


def resolve_workspace_path(raw_workspace: str | None) -> Path:
    workspace = raw_workspace or os.getcwd()
    return Path(workspace).expanduser().resolve()


def has_explicit_config_arg(engine_args: list[str]) -> bool:
    return any(arg == "--config" or arg.startswith("--config=") for arg in engine_args)


def is_help_request(engine_args: list[str]) -> bool:
    return any(arg in {"-h", "--help"} for arg in engine_args)


def is_skill_backend_repo(path: Path) -> bool:
    return all(
        (path / entry).exists()
        for entry in (
            "SKILL.md",
            "engine",
            "engine/cli.py",
            "engine/data/lucide-index.json",
            "engine/scripts/run_skill_backend.py",
        )
    )


def is_valid_generation_config(path: Path) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(raw, dict):
        return False

    target_dir = str(raw.get("target_dir", "")).strip()
    package_name = str(raw.get("package", "")).strip()
    object_class_extension = raw.get("object_class_extension", "")
    if not target_dir or not Path(target_dir).is_absolute():
        return False
    if not package_name:
        return False
    return isinstance(object_class_extension, str)


def find_project_config(workspace_root: Path) -> Path | None:
    for directory in (workspace_root, *workspace_root.parents):
        for relative_path in PROJECT_CONFIG_CANDIDATES:
            candidate = directory / relative_path
            if not candidate.is_file():
                continue
            if candidate.name == "config.json" and is_skill_backend_repo(directory):
                continue
            if is_valid_generation_config(candidate):
                return candidate
    return None


def inject_project_config(engine_args: list[str], config_path: Path) -> list[str]:
    return [engine_args[0], "--config", str(config_path), *engine_args[1:]]


def resolve_engine_args(engine_args: list[str], workspace_root: Path) -> list[str]:
    if not engine_args or engine_args[0] != "generate":
        return engine_args
    if has_explicit_config_arg(engine_args):
        return engine_args
    if os.environ.get(CONFIG_ENV_VAR, "").strip():
        return engine_args
    if is_help_request(engine_args):
        return engine_args

    project_config = find_project_config(workspace_root)
    if project_config is not None:
        print(f"使用项目配置: {project_config}", file=sys.stderr)
        return inject_project_config(engine_args, project_config)

    raise SystemExit(
        "生成图标时未找到项目配置。"
        " 请显式传入 --config，或在当前项目目录/父目录中放置以下任一文件："
        " lucide-icons-compose.config.json、.codex/lucide-icons-compose.json、config.json"
    )


def ensure_generate_runtime(skill_backend_root: Path, engine_args: list[str]) -> None:
    if not engine_args or engine_args[0] != "generate":
        return
    if is_valkyrie_runtime_ready(skill_backend_root):
        return

    valkyrie_dir = skill_backend_root / "engine" / "valkyrie-cli"
    raise SystemExit(
        "当前 backend 缺少可用的 Valkyrie CLI，无法执行 generate。\n"
        f"缺失路径: {valkyrie_dir}\n"
        "请将官方 release 解压到该目录，"
        "或使用带有 engine/valkyrie-cli 的本地 backend 通过 --backend-path 重新播种缓存。"
    )


def run_skill_backend() -> int:
    parser = argparse.ArgumentParser(
        description="通过可自举 backend 运行 lucide-icons-compose-skill。",
    )
    parser.add_argument("--workspace", help="搜索 backend 仓库的起始目录")
    parser.add_argument("--backend-path", help="显式指定 backend 仓库根目录")
    parser.add_argument(
        "--backend-env-var",
        default=DEFAULT_BACKEND_ENV_VAR,
        help="读取 backend 根目录的环境变量名",
    )
    parser.add_argument(
        "--remote-url",
        help="backend 远端仓库 URL，默认使用 skill 内置地址",
    )
    parser.add_argument(
        "--remote-url-env-var",
        default="LUCIDE_ICONS_COMPOSE_SKILL_REPO_URL",
        help="读取 backend 远端仓库 URL 的环境变量名",
    )
    parser.add_argument(
        "--refresh-from-remote",
        action="store_true",
        help="忽略已有缓存，强制从远端重新克隆 backend",
    )
    parser.add_argument(
        "--print-backend-path",
        action="store_true",
        help="仅打印最终使用的 backend 路径",
    )
    parser.add_argument(
        "engine_args",
        nargs=argparse.REMAINDER,
        help="传递给 backend 的参数，例如 generate arrow-left",
    )
    args = parser.parse_args()

    skill_backend_root, _ = resolve_skill_backend(args)
    workspace_root = resolve_workspace_path(args.workspace)
    if args.print_backend_path:
        print(skill_backend_root)
        return 0

    engine_args = list(args.engine_args)
    if engine_args and engine_args[0] == "--":
        engine_args = engine_args[1:]
    if not engine_args:
        parser.error("缺少 backend 参数，例如 search arrow 或 generate arrow-left")
    engine_args = resolve_engine_args(engine_args, workspace_root)
    ensure_generate_runtime(skill_backend_root, engine_args)

    command = get_skill_backend_command(skill_backend_root) + engine_args
    process = subprocess.run(
        command,
        cwd=str(skill_backend_root),
        env=build_skill_backend_env(skill_backend_root),
    )
    return process.returncode


def main() -> int:
    return run_skill_backend()


if __name__ == "__main__":
    sys.exit(main())
