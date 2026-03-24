#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .lucide_index import (
    LUCIDE_INDEX_PATH,
    fetch_icon_svg as lucide_fetch_icon_svg,
    find_icon as lucide_find_icon,
    list_categories as lucide_list_categories,
    search_icons as lucide_search_icons,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
ENGINE_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / ".cache"
CACHE_TEMP_DIR = CACHE_DIR / "tmp"
CACHE_LUCIDE_DIR = CACHE_DIR / "lucide"
CACHE_LUCIDE_SVG_DIR = CACHE_LUCIDE_DIR / "svg"
VALKYRIE_RELEASE_DIR = ENGINE_DIR / "valkyrie-cli"
VALKYRIE_RELEASE_BIN_DIR = VALKYRIE_RELEASE_DIR / "bin"
OBJECT_DECLARATION_TEMPLATE = "package {package_name}\n\nobject {object_name}\n"
KOTLIN_OBJECT_PATTERN = r"\bobject\s+{name}\b"
KOTLIN_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONFIG_ENV_VAR = "LUCIDE_ICONS_COMPOSE_CONFIG"


class EngineError(RuntimeError):
    pass


def is_windows() -> bool:
    return os.name == "nt"


def ensure_cache_dirs() -> None:
    CACHE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_LUCIDE_SVG_DIR.mkdir(parents=True, exist_ok=True)


def build_command_env() -> dict[str, str]:
    ensure_cache_dirs()
    env = os.environ.copy()
    temp_dir = str(CACHE_TEMP_DIR.resolve())
    env["TMP"] = temp_dir
    env["TEMP"] = temp_dir
    env["TMPDIR"] = temp_dir
    return env


def get_valkyrie_binary_name() -> str:
    return "valkyrie.bat" if is_windows() else "valkyrie"


def get_valkyrie_release_bin_path() -> Path:
    return VALKYRIE_RELEASE_BIN_DIR / get_valkyrie_binary_name()


def is_valkyrie_runtime_ready(valkyrie_bin: Path) -> bool:
    if not valkyrie_bin.exists():
        return False
    install_dir = valkyrie_bin.parent.parent
    return (install_dir / "lib").exists()


def find_valkyrie_runtime() -> Path | None:
    release_valkyrie_bin = get_valkyrie_release_bin_path()
    if is_valkyrie_runtime_ready(release_valkyrie_bin):
        return release_valkyrie_bin
    return None


def get_valkyrie_command(valkyrie_bin: Path) -> list[str]:
    if is_windows():
        return [str(valkyrie_bin)]
    return ["sh", str(valkyrie_bin)]


@dataclass
class GenerationConfig:
    target_dir: Path
    package_name: str
    object_class_extension: str
    output_dir: Path
    object_file: Path | None
    object_name: str | None


def run_command(command: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
        env=build_command_env(),
    )


def print_command_output(process: subprocess.CompletedProcess[str]) -> None:
    if process.stdout.strip():
        print(process.stdout.rstrip())
    if process.stderr.strip():
        print(process.stderr.rstrip(), file=sys.stderr)


def resolve_config_path(config_arg: str | None) -> Path:
    config_value = config_arg or os.environ.get(CONFIG_ENV_VAR, "").strip()
    if not config_value:
        raise EngineError(
            "生成图标需要显式配置。"
            f" 请通过 --config 或环境变量 {CONFIG_ENV_VAR} 指定配置文件路径。"
        )

    config_path = Path(config_value).expanduser()
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    return config_path


def load_config(config_path: Path | None = None) -> GenerationConfig:
    if config_path is None:
        raise EngineError("缺少配置文件路径。")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EngineError(f"未找到配置文件: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise EngineError(f"配置文件不是合法 JSON: {exc}") from exc

    target_dir_raw = str(raw.get("target_dir", "")).strip()
    package_name = str(raw.get("package", "")).strip()
    object_class_extension = str(raw.get("object_class_extension", "")).strip()

    if not target_dir_raw:
        raise EngineError("配置中的 target_dir 不能为空")
    target_dir = Path(target_dir_raw)
    if not target_dir.is_absolute():
        raise EngineError(f"target_dir 必须是绝对路径: {target_dir}")

    if not package_name:
        raise EngineError("配置中的 package 不能为空")

    output_dir = target_dir.joinpath(*package_name.split("."))

    object_file: Path | None = None
    object_name: str | None = None
    if object_class_extension:
        if Path(object_class_extension).name != object_class_extension:
            raise EngineError("object_class_extension 必须是文件名，不能包含目录")
        if not object_class_extension.lower().endswith(".kt"):
            raise EngineError("object_class_extension 必须是 Kotlin 文件名，例如 Icons.kt")
        object_name = Path(object_class_extension).stem
        if not KOTLIN_IDENTIFIER_PATTERN.match(object_name):
            raise EngineError(f"object_class_extension 推导出的对象名不合法: {object_name}")
        object_file = output_dir / object_class_extension

    return GenerationConfig(
        target_dir=target_dir,
        package_name=package_name,
        object_class_extension=object_class_extension,
        output_dir=output_dir,
        object_file=object_file,
        object_name=object_name,
    )


def ensure_lucide_index_ready() -> Path:
    if LUCIDE_INDEX_PATH.exists():
        return LUCIDE_INDEX_PATH
    raise EngineError(
        f"未找到 Lucide 索引文件: {LUCIDE_INDEX_PATH}。"
        "请先运行 `python -m engine.update_lucide_index`。"
    )


def ensure_valkyrie_ready() -> Path:
    runtime = find_valkyrie_runtime()
    if runtime is not None:
        return runtime
    raise EngineError(
        "未找到可用的 Valkyrie CLI。请将官方 release 解压到 engine/valkyrie-cli/，"
        "并确保其中包含 bin/ 与 lib/ 目录。"
    )


def search_icons(query: str, category: str | None, limit: int) -> list[dict[str, Any]]:
    ensure_lucide_index_ready()
    try:
        return lucide_search_icons(query=query, category=category, limit=limit, index_path=LUCIDE_INDEX_PATH)
    except RuntimeError as exc:
        raise EngineError(str(exc)) from exc


def find_icon(name: str) -> dict[str, Any] | None:
    ensure_lucide_index_ready()
    try:
        return lucide_find_icon(name=name, index_path=LUCIDE_INDEX_PATH)
    except RuntimeError as exc:
        raise EngineError(str(exc)) from exc


def list_categories() -> list[str]:
    ensure_lucide_index_ready()
    try:
        return lucide_list_categories(index_path=LUCIDE_INDEX_PATH)
    except RuntimeError as exc:
        raise EngineError(str(exc)) from exc


def resolve_icon(query: str, category: str | None, select: int | None) -> dict[str, Any]:
    exact = find_icon(query)
    if exact is not None:
        return exact

    results = search_icons(query=query, category=category, limit=10)
    if not results:
        raise EngineError(f"未找到图标: {query}")

    if select is not None:
        if select < 1 or select > len(results):
            raise EngineError(f"--select 超出候选范围: 1..{len(results)}")
        return results[select - 1]["icon"]

    if len(results) == 1:
        return results[0]["icon"]

    lines = [f"图标名存在歧义，请使用精确 slug/name 或追加 --select：{query}", ""]
    for index, result in enumerate(results, start=1):
        icon = result["icon"]
        categories = ", ".join(icon["categories"])
        lines.append(f"{index}. {icon['name']} ({icon['slug']})  score={result['score']}  categories={categories}")
    raise EngineError("\n".join(lines))


def ensure_object_file(config: GenerationConfig) -> None:
    if config.object_file is None or config.object_name is None:
        return

    config.output_dir.mkdir(parents=True, exist_ok=True)
    if not config.object_file.exists():
        config.object_file.write_text(
            OBJECT_DECLARATION_TEMPLATE.format(
                package_name=config.package_name,
                object_name=config.object_name,
            ),
            encoding="utf-8",
        )
        print(f"已创建对象承载文件: {config.object_file}")
        return

    content = config.object_file.read_text(encoding="utf-8")
    package_pattern = re.compile(rf"^\s*package\s+{re.escape(config.package_name)}\s*$", re.MULTILINE)
    if not package_pattern.search(content):
        raise EngineError(
            f"对象承载文件 package 不正确，应为 {config.package_name}: {config.object_file}"
        )
    object_pattern = re.compile(KOTLIN_OBJECT_PATTERN.format(name=re.escape(config.object_name)))
    if not object_pattern.search(content):
        raise EngineError(
            f"对象承载文件已存在但不包含 object {config.object_name}: {config.object_file}"
        )


def ensure_icon_svg(icon: dict[str, Any]) -> Path:
    ensure_cache_dirs()
    svg_path = CACHE_LUCIDE_SVG_DIR / f"{icon['slug']}.svg"
    if svg_path.exists() and svg_path.stat().st_size > 0:
        return svg_path

    try:
        svg_content = lucide_fetch_icon_svg(str(icon["slug"]))
    except RuntimeError as exc:
        raise EngineError(str(exc)) from exc

    svg_path.write_text(svg_content, encoding="utf-8")
    return svg_path


def run_valkyrie(config: GenerationConfig, icon: dict[str, Any], svg_path: Path) -> Path:
    valkyrie_bin = ensure_valkyrie_ready()
    config.output_dir.mkdir(parents=True, exist_ok=True)

    command = get_valkyrie_command(valkyrie_bin) + [
        "svgxml2imagevector",
        "--input-path",
        str(svg_path),
        "--output-path",
        str(config.output_dir),
        "--package-name",
        config.package_name,
    ]
    if config.object_name:
        command.extend(["--iconpack-name", config.object_name])

    process = run_command(command, cwd=ROOT_DIR)
    print_command_output(process)
    return config.output_dir / f"{icon['name']}.kt"


def verify_output(config: GenerationConfig, icon: dict[str, Any], output_file: Path) -> None:
    if not output_file.exists():
        raise EngineError(f"未找到生成结果: {output_file}")

    resolved_output_dir = config.output_dir.resolve()
    resolved_output_file = output_file.resolve()
    if resolved_output_dir not in resolved_output_file.parents:
        raise EngineError(f"输出文件未落在目标包目录下: {output_file}")

    content = output_file.read_text(encoding="utf-8")
    package_pattern = re.compile(rf"^\s*package\s+{re.escape(config.package_name)}\s*$", re.MULTILINE)
    if not package_pattern.search(content):
        raise EngineError(f"生成文件 package 不正确: {output_file}")

    if config.object_name:
        expected = f"val {config.object_name}.{icon['name']}: ImageVector"
        if expected not in content:
            raise EngineError(f"生成结果不是期望的扩展属性: {output_file}")


def cmd_categories(_: argparse.Namespace) -> int:
    for category in list_categories():
        print(category)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    results = search_icons(query=query, category=args.category, limit=args.limit)
    if not results:
        print("未找到匹配图标。")
        return 1

    for index, result in enumerate(results, start=1):
        icon = result["icon"]
        categories = ", ".join(icon["categories"])
        tags = ", ".join(icon["tags"][:5])
        print(f"{index}. {icon['name']} ({icon['slug']})")
        print(f"   score: {result['score']}")
        print(f"   categories: {categories}")
        print(f"   tags: {tags}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    icon_query = " ".join(args.icon)
    icon = resolve_icon(query=icon_query, category=args.category, select=args.select)

    ensure_object_file(config)
    ensure_cache_dirs()
    svg_path = ensure_icon_svg(icon=icon)
    output_file = run_valkyrie(config=config, icon=icon, svg_path=svg_path)
    verify_output(config=config, icon=icon, output_file=output_file)

    print(f"已生成图标: {icon['name']} ({icon['slug']})")
    print(f"配置文件: {config_path}")
    print(f"输出目录: {config.output_dir}")
    print(f"输出文件: {output_file}")
    if config.object_file is not None:
        print(f"对象文件: {config.object_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lucide -> Compose ImageVector 后端执行脚本",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    categories_parser = subparsers.add_parser("categories", help="列出 Lucide 分类")
    categories_parser.set_defaults(func=cmd_categories)

    search_parser = subparsers.add_parser("search", help="搜索 Lucide 图标")
    search_parser.add_argument("query", nargs="+", help="搜索词")
    search_parser.add_argument("--category", help="分类过滤")
    search_parser.add_argument("--limit", type=int, default=10, help="返回数量上限")
    search_parser.set_defaults(func=cmd_search)

    generate_parser = subparsers.add_parser("generate", help="生成单个 Lucide 图标")
    generate_parser.add_argument("icon", nargs="+", help="精确图标名、slug，或待搜索的查询词")
    generate_parser.add_argument("--category", help="搜索时使用的分类过滤")
    generate_parser.add_argument(
        "--config",
        help=(
            "配置文件路径。"
            f"也可通过环境变量 {CONFIG_ENV_VAR} 指定"
        ),
    )
    generate_parser.add_argument("--select", type=int, help="当搜索有多个候选时，选择第几个结果")
    generate_parser.set_defaults(func=cmd_generate)

    return parser


def main() -> int:
    try:
        parser = build_parser()
        args = parser.parse_args()
        return args.func(args)
    except EngineError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        if exc.stdout:
            print(exc.stdout.rstrip())
        if exc.stderr:
            print(exc.stderr.rstrip(), file=sys.stderr)
        print(f"错误: 命令执行失败: {' '.join(exc.cmd)}", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    sys.exit(main())
