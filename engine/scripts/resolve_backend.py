#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path


REQUIRED_BACKEND_ENTRIES = (
    "SKILL.md",
    "engine",
    "engine/cli.py",
    "engine/data/lucide-index.json",
    "engine/scripts/resolve_backend.py",
    "engine/scripts/run_skill_backend.py",
)
DEFAULT_BACKEND_ENV_VAR = "LUCIDE_ICONS_COMPOSE_SKILL_BACKEND"
DEFAULT_REMOTE_URL = "https://github.com/GangJust/lucide-icons-compose-skill"
DEFAULT_REMOTE_URL_ENV_VAR = "LUCIDE_ICONS_COMPOSE_SKILL_REPO_URL"
SHORT_CACHE_DIRNAME = "lics"
LOCK_TIMEOUT_SEC = 120.0
LOCK_POLL_INTERVAL_SEC = 0.2


def resolve_workspace_root(raw_workspace: str | None) -> Path:
    workspace = raw_workspace or os.getcwd()
    return Path(workspace).expanduser().resolve()


def get_project_cache_skill_backend_root(workspace_root: Path) -> Path:
    return workspace_root / ".cache" / SHORT_CACHE_DIRNAME / "backend"


def get_project_cache_skill_backend_lock_root(workspace_root: Path) -> Path:
    return workspace_root / ".cache" / SHORT_CACHE_DIRNAME / "backend.lock"


def is_skill_backend_repo(path: Path) -> bool:
    return path.is_dir() and all((path / entry).exists() for entry in REQUIRED_BACKEND_ENTRIES)


def find_skill_backend_ancestors(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if is_skill_backend_repo(candidate):
            return candidate
    return None


def build_ignore_names() -> set[str]:
    return {
        ".cache",
        ".git",
        "__pycache__",
        "build",
        "dist",
    }


def should_ignore_dir(name: str, parent: Path) -> bool:
    if name not in build_ignore_names():
        return False
    if name == "build" and parent.name not in {"cli", "tools"}:
        return False
    return True


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def acquire_cache_backend_lock(workspace_root: Path):
    lock_root = get_project_cache_skill_backend_lock_root(workspace_root)
    lock_root.parent.mkdir(parents=True, exist_ok=True)
    owner_path = lock_root / "owner.json"
    owner_payload = {
        "pid": os.getpid(),
        "time": time.time(),
        "cwd": str(Path.cwd()),
    }
    started_at = time.monotonic()

    while True:
        try:
            lock_root.mkdir(exist_ok=False)
            owner_path.write_text(json.dumps(owner_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            break
        except FileExistsError:
            if time.monotonic() - started_at >= LOCK_TIMEOUT_SEC:
                raise SystemExit(
                    "等待 backend 缓存锁超时。"
                    f" 请检查是否有其他进程正在使用 {lock_root.parent / 'backend'}，"
                    f" 或清理残留锁目录: {lock_root}"
                )
            time.sleep(LOCK_POLL_INTERVAL_SEC)

    try:
        yield
    finally:
        if owner_path.exists():
            owner_path.unlink(missing_ok=True)
        if lock_root.exists():
            try:
                lock_root.rmdir()
            except OSError:
                pass


def build_staging_path(target: Path) -> Path:
    suffix = f"{os.getpid()}-{time.time_ns()}"
    return target.parent / f".{target.name}.staging-{suffix}"


def build_backup_path(target: Path) -> Path:
    suffix = f"{os.getpid()}-{time.time_ns()}"
    return target.parent / f".{target.name}.backup-{suffix}"


def install_staged_backend(staging: Path, target: Path) -> None:
    backup: Path | None = None
    try:
        if target.exists():
            backup = build_backup_path(target)
            target.rename(backup)
        staging.rename(target)
    except OSError as exc:
        if backup is not None and backup.exists() and not target.exists():
            backup.rename(target)
        remove_tree(staging)
        raise SystemExit(
            "无法切换 backend 缓存目录。"
            f" 目标路径可能正被其他进程占用: {target}\n{exc}"
        ) from exc
    finally:
        if backup is not None and backup.exists():
            remove_tree(backup)


def copy_skill_backend_tree(source: Path, target: Path) -> None:
    ignore_names = build_ignore_names()

    def ignore(path_str: str, names: list[str]) -> set[str]:
        parent = Path(path_str)
        ignored: set[str] = set()
        for name in names:
            if name in ignore_names and should_ignore_dir(name, parent):
                ignored.add(name)
        return ignored

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = build_staging_path(target)
    remove_tree(staging)
    try:
        shutil.copytree(source, staging, ignore=ignore)
        if not is_skill_backend_repo(staging):
            raise SystemExit(f"复制后的 backend 内容不符合约定: {source}")
        install_staged_backend(staging, target)
    finally:
        remove_tree(staging)


def get_remote_url(args: argparse.Namespace) -> str:
    remote_url = getattr(args, "remote_url", "") or os.environ.get(
        getattr(args, "remote_url_env_var", DEFAULT_REMOTE_URL_ENV_VAR),
        "",
    ).strip()
    return remote_url or DEFAULT_REMOTE_URL


def clone_skill_backend_from_remote(remote_url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = build_staging_path(target)
    remove_tree(staging)
    process = subprocess.run(
        ["git", "clone", remote_url, str(staging)],
        text=True,
        capture_output=True,
    )
    if process.returncode != 0:
        remove_tree(staging)
        stderr = process.stderr.strip()
        stdout = process.stdout.strip()
        details = stderr or stdout or "git clone 失败"
        raise SystemExit(f"无法从远端克隆 backend: {remote_url}\n{details}")
    if not is_skill_backend_repo(staging):
        remove_tree(staging)
        raise SystemExit(f"远端仓库克隆完成，但内容不符合 backend 约定: {remote_url}")
    install_staged_backend(staging, target)


def parse_skill_backend_candidates(args: argparse.Namespace) -> list[Path]:
    candidates: list[Path] = []

    explicit = args.backend_path or os.environ.get(args.backend_env_var, "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser().resolve())

    workspace_root = resolve_workspace_root(args.workspace)
    direct_workspace_match = find_skill_backend_ancestors(workspace_root)
    if direct_workspace_match is not None:
        candidates.append(direct_workspace_match)

    cache_backend = get_project_cache_skill_backend_root(workspace_root)
    if is_skill_backend_repo(cache_backend):
        candidates.append(cache_backend)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def resolve_skill_backend(args: argparse.Namespace) -> tuple[Path, bool]:
    workspace_root = resolve_workspace_root(args.workspace)
    cache_backend = get_project_cache_skill_backend_root(workspace_root)
    remote_url = get_remote_url(args)
    refresh_from_remote = bool(getattr(args, "refresh_from_remote", False))
    explicit = args.backend_path or os.environ.get(args.backend_env_var, "").strip()
    if explicit:
        explicit_path = Path(explicit).expanduser().resolve()
        if not is_skill_backend_repo(explicit_path):
            raise SystemExit(f"显式指定的 backend 无效: {explicit_path}")
        if explicit_path == cache_backend:
            return cache_backend, False
        if workspace_root == explicit_path or workspace_root in explicit_path.parents:
            return explicit_path, False
        with acquire_cache_backend_lock(workspace_root):
            copy_skill_backend_tree(explicit_path, cache_backend)
            return cache_backend, True

    if refresh_from_remote:
        with acquire_cache_backend_lock(workspace_root):
            clone_skill_backend_from_remote(remote_url, cache_backend)
            return cache_backend, True

    direct_workspace_match = find_skill_backend_ancestors(workspace_root)
    if direct_workspace_match is not None and workspace_root == direct_workspace_match:
        return direct_workspace_match, False

    with acquire_cache_backend_lock(workspace_root):
        if is_skill_backend_repo(cache_backend):
            return cache_backend, False

        for candidate in parse_skill_backend_candidates(args):
            if candidate == cache_backend:
                return cache_backend, False
            if workspace_root == candidate or workspace_root in candidate.parents:
                return candidate, False
            if is_skill_backend_repo(candidate):
                copy_skill_backend_tree(candidate, cache_backend)
                return cache_backend, True

        clone_skill_backend_from_remote(remote_url, cache_backend)
        return cache_backend, True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="定位或缓存 lucide-icons-compose-skill backend 仓库。",
    )
    parser.add_argument(
        "--workspace",
        help="搜索 backend 仓库的起始目录，默认使用当前工作目录",
    )
    parser.add_argument(
        "--backend-path",
        help="显式指定 backend 仓库根目录",
    )
    parser.add_argument(
        "--backend-env-var",
        default=DEFAULT_BACKEND_ENV_VAR,
        help="读取 backend 根目录的环境变量名",
    )
    parser.add_argument(
        "--remote-url",
        help="backend 远端仓库 URL，默认使用内置 GitHub 仓库地址",
    )
    parser.add_argument(
        "--remote-url-env-var",
        default=DEFAULT_REMOTE_URL_ENV_VAR,
        help="读取 backend 远端仓库 URL 的环境变量名",
    )
    parser.add_argument(
        "--refresh-from-remote",
        action="store_true",
        help="忽略已有缓存，强制从远端重新克隆 backend",
    )
    parser.add_argument(
        "--print-cache-path",
        action="store_true",
        help="打印当前项目 .cache 中的 backend 路径",
    )
    args = parser.parse_args()

    backend_path, seeded = resolve_skill_backend(args)
    if args.print_cache_path:
        print(backend_path)
    else:
        state = "seeded" if seeded else "reused"
        print(f"{state}:{backend_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
