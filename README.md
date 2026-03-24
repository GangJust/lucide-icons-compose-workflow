# lucide-icons-compose-skill

`lucide-icons-compose-skill` 是 `lucide-icons-compose-skill` 的实现仓库，用于完成两件事：

- 搜索 Lucide 图标并获取准确的 SVG
- 调用 Valkyrie CLI 生成 Jetpack Compose `ImageVector`

## 目录

```text
.
├── SKILL.md
├── references/
│   └── backend-contract.md
├── agents/
│   └── openai.yaml
└── engine/
    ├── __init__.py
    ├── cli.py
    ├── lucide_index.py
    ├── update_lucide_index.py
    ├── scripts/
    │   ├── resolve_backend.py
    │   └── run_skill_backend.py
    ├── data/
    │   └── lucide-index.json
    └── valkyrie-cli/
```

关键文件：

- [SKILL.md](./SKILL.md)：skill 入口说明
- [references/backend-contract.md](./references/backend-contract.md)：backend 契约
- [engine/scripts/run_skill_backend.py](./engine/scripts/run_skill_backend.py)：backend 自举与执行入口
- [engine/cli.py](./engine/cli.py)：backend CLI 主实现
- [engine/lucide_index.py](./engine/lucide_index.py)：Lucide 索引、搜索与 SVG 获取
- [engine/data/lucide-index.json](./engine/data/lucide-index.json)：本地 Lucide 元数据索引

## 使用方式

通过 skill backend 入口：

```bash
python engine/scripts/run_skill_backend.py search arrow left
python engine/scripts/run_skill_backend.py generate arrow-left --config /path/to/config.json
```

这个 helper 会禁止把自己的 `__pycache__` 写回仓库目录；实际 backend 执行产生的字节码和临时文件会落到当前项目 `.cache/` 子树下。

直接调试 backend：

```bash
python -X pycache_prefix=.cache/pycache -m engine.cli search arrow left
python -X pycache_prefix=.cache/pycache -m engine.cli generate arrow-left --config /path/to/config.json
```

## 配置

生成命令必须由调用方显式提供配置文件，或者通过环境变量 `LUCIDE_ICONS_COMPOSE_CONFIG` 指定。

推荐在调用方项目根目录放置：

- `lucide-icons-compose.config.json`

配置文件字段：

- `target_dir`：Kotlin 源码输出根目录，必须是绝对路径
- `package`：输出包名
- `object_class_extension`：可选的承载对象文件名，例如 `Icons.kt`

当 `object_class_extension` 非空时，工作流会在目标包目录下校验或创建最小 `object` 承载文件，然后生成扩展属性形式的 `ImageVector`。

最小配置示例：

```json
{
  "target_dir": "D:\\Code\\Demo\\src\\commonMain\\kotlin",
  "package": "io.github.lucide.icons",
  "object_class_extension": "Icons.kt"
}
```

对应的项目侧 `lucide-icons-compose.config.json` 可以直接写成：

```json
{
  "target_dir": "D:\\Code\\Demo\\src\\commonMain\\kotlin",
  "package": "io.github.lucide.icons",
  "object_class_extension": "Icons.kt"
}
```

## 项目侧 AGENTS.md

如果通过 Codex 在业务项目里调用这个 skill，推荐在项目根目录放一个最小 `AGENTS.md`，明确告诉调用方去哪里读配置、生成结果应该满足什么约束。

示例：

```md
# Project Instructions

- 生成 Lucide Compose 图标时使用 `$lucide-icons-compose-skill`
- 生成前先读取项目根 `lucide-icons-compose.config.json`
- 输出目录必须是 `target_dir + package路径`
- 如果 `object_class_extension` 非空，先确保目标包目录下存在对应 Kotlin 承载文件
- 如果 `object_class_extension = Icons.kt`，生成结果必须是 `val Icons.IconName: ImageVector`
- 若搜索结果不唯一，不要静默猜测，必须显式选择候选
```

对应的最小 Kotlin 承载文件可以是：

```kt
package io.github.lucide.icons

object Icons
```

生成结果应类似：

```kt
package io.github.lucide.icons

import androidx.compose.ui.graphics.vector.ImageVector

val Icons.ArrowLeft: ImageVector
    get() = TODO()
```

## Lucide 索引

本仓库使用 [engine/data/lucide-index.json](./engine/data/lucide-index.json) 提供本地 Lucide 搜索能力。

刷新索引：

```bash
python -m engine.update_lucide_index
```

## 缓存

通过 skill 使用时，所有缓存、临时文件和 Python 字节码都写入调用方项目根目录 `.cache/` 子树下，包括：

- Python `pycache`
- 临时 SVG 文件
- Lucide SVG 缓存
- 其他中间产物

如果 backend 被种到调用方项目的 `.cache/lics/backend`，那么 backend 自己的临时目录会继续位于该缓存副本内部的 `.cache/`，例如 `.cache/lics/backend/.cache/pycache`。
当多个进程同时尝试播种或刷新同一个 backend 缓存时，helper 会使用同级的 `backend.lock` 串行化这一步。

## Runtime Dependencies

- Python 3.10+
- Java 21+
- `engine/valkyrie-cli/` 官方 release 运行时

说明：

- `engine/valkyrie-cli/` 不随 Git 远端自动提供
- 如果使用远端克隆或项目缓存中的 backend 执行 `generate`，需要先在该 backend 根目录下准备好 `engine/valkyrie-cli/`
- 也可以直接用带有该运行时的本地 backend 通过 `--backend-path` 重新播种缓存

## Upstream References

- [lucide-icons-mcp-server](https://github.com/matracey/lucide-icons-mcp-server)
- [Valkyrie](https://github.com/ComposeGears/Valkyrie)
