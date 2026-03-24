from __future__ import annotations

import argparse
from pathlib import Path

from .lucide_index import LUCIDE_INDEX_PATH, write_index


def main() -> int:
    parser = argparse.ArgumentParser(description="更新本地 Lucide 图标元数据索引。")
    parser.add_argument(
        "--output",
        help=f"输出文件路径，默认使用 {LUCIDE_INDEX_PATH}",
    )
    args = parser.parse_args()

    output_path = Path(args.output).expanduser().resolve() if args.output else LUCIDE_INDEX_PATH
    written_path = write_index(output_path)
    print(f"已更新 Lucide 索引: {written_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
