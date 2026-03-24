from __future__ import annotations

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENGINE_DIR = Path(__file__).resolve().parent
ROOT_DIR = ENGINE_DIR.parent
LUCIDE_INDEX_PATH = ENGINE_DIR / "data" / "lucide-index.json"
LUCIDE_CATEGORIES_URL = "https://lucide.dev/api/categories"
LUCIDE_TAGS_URL = "https://lucide.dev/api/tags"
LUCIDE_SVG_BASE_URL = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons"
HTTP_TIMEOUT_SEC = 30
MAX_SEARCH_RESULTS = 20
USER_AGENT = "lucide-icons-compose-skill"


def kebab_to_pascal(kebab: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in kebab.split("-"))


def _fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SEC) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"请求失败: {url} HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"请求失败: {url} {exc.reason}") from exc


def _fetch_json(url: str) -> Any:
    return json.loads(_fetch_text(url))


def _normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return sorted(dict.fromkeys(normalized))


def build_index_payload(
    categories_data: dict[str, list[str]],
    tags_data: dict[str, list[str]],
) -> dict[str, Any]:
    icon_names = sorted(categories_data.keys())
    icons: list[dict[str, Any]] = []
    for slug in icon_names:
        icons.append(
            {
                "name": kebab_to_pascal(slug),
                "slug": slug,
                "categories": _normalize_text_list(categories_data.get(slug, [])),
                "tags": _normalize_text_list(tags_data.get(slug, [])),
            }
        )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sources": {
            "categories": LUCIDE_CATEGORIES_URL,
            "tags": LUCIDE_TAGS_URL,
            "svg_base": LUCIDE_SVG_BASE_URL,
        },
        "icons": icons,
    }


def fetch_remote_index_payload() -> dict[str, Any]:
    categories_data = _fetch_json(LUCIDE_CATEGORIES_URL)
    tags_data = _fetch_json(LUCIDE_TAGS_URL)
    if not isinstance(categories_data, dict) or not isinstance(tags_data, dict):
        raise RuntimeError("Lucide API 返回格式不符合预期")
    return build_index_payload(categories_data, tags_data)


def write_index(path: Path = LUCIDE_INDEX_PATH) -> Path:
    payload = fetch_remote_index_payload()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_index_payload.cache_clear()
    return path


@lru_cache(maxsize=1)
def load_index_payload(path_str: str = "") -> dict[str, Any]:
    path = Path(path_str) if path_str else LUCIDE_INDEX_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"未找到 Lucide 索引文件: {path}。"
            "请先运行 `python -m engine.update_lucide_index`。"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Lucide 索引文件不是合法 JSON: {path}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("icons"), list):
        raise RuntimeError(f"Lucide 索引文件结构不符合预期: {path}")
    return payload


def load_icons(index_path: Path = LUCIDE_INDEX_PATH) -> list[dict[str, Any]]:
    payload = load_index_payload(str(index_path.resolve()))
    icons = payload["icons"]
    if not isinstance(icons, list):
        raise RuntimeError(f"Lucide 索引 icons 字段不符合预期: {index_path}")
    return icons


def search_icons(
    query: str,
    category: str | None = None,
    limit: int = 10,
    index_path: Path = LUCIDE_INDEX_PATH,
) -> list[dict[str, Any]]:
    icons = load_icons(index_path)
    query_lower = query.lower().strip()
    if not query_lower:
        return []

    tokens = [token for token in query_lower.split() if token]
    filtered = icons
    if category:
        filtered = [icon for icon in icons if category in icon.get("categories", [])]

    results: list[dict[str, Any]] = []
    for icon in filtered:
        score = 0
        matched_on: set[str] = set()
        name_lower = str(icon["name"]).lower()
        slug_lower = str(icon["slug"])

        if name_lower == query_lower or slug_lower == query_lower:
            score += 100
            matched_on.add("name")
        elif query_lower in name_lower or query_lower in slug_lower:
            score += 50
            matched_on.add("name")

        for token in tokens:
            if (token in name_lower or token in slug_lower) and "name" not in matched_on:
                score += 30
                matched_on.add("name")

        for tag in icon.get("tags", []):
            tag_lower = str(tag).lower()
            matched = False
            for token in tokens:
                if tag_lower == token:
                    score += 20
                    matched_on.add("tags")
                    matched = True
                    break
                if token in tag_lower:
                    score += 10
                    matched_on.add("tags")
                    matched = True
                    break
            if matched:
                break

        for icon_category in icon.get("categories", []):
            category_lower = str(icon_category).lower()
            matched = False
            for token in tokens:
                if category_lower == token or token in category_lower:
                    score += 15
                    matched_on.add("categories")
                    matched = True
                    break
            if matched:
                break

        if score > 0:
            results.append(
                {
                    "icon": icon,
                    "score": score,
                    "matchedOn": sorted(matched_on),
                }
            )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: min(limit, MAX_SEARCH_RESULTS)]


def find_icon(name: str, index_path: Path = LUCIDE_INDEX_PATH) -> dict[str, Any] | None:
    name_lower = name.lower()
    for icon in load_icons(index_path):
        if str(icon["name"]).lower() == name_lower or str(icon["slug"]) == name_lower:
            return icon
    return None


def list_categories(index_path: Path = LUCIDE_INDEX_PATH) -> list[str]:
    categories: set[str] = set()
    for icon in load_icons(index_path):
        categories.update(str(category) for category in icon.get("categories", []))
    return sorted(categories)


def fetch_icon_svg(slug: str) -> str:
    return _fetch_text(f"{LUCIDE_SVG_BASE_URL}/{slug}.svg")
