# lucide-icons-compose-skill

## 通用指令

- 采用中文沟通。
- 这个仓库只作为 `lucide-icons-compose-skill` 的源码与 backend 仓库。
- 所有缓存、临时文件、Python `pycache`、SVG 缓存都必须统一放在根目录 `.cache/` 下。

## 仓库分层

- 根目录放 skill 资源与稳定入口：
  `SKILL.md`、`references/`、`agents/`
- 具体 backend 逻辑统一放在 `engine/`
- Lucide 本地索引文件位于 [engine/data/lucide-index.json](engine/data/lucide-index.json)
- Compose 转换运行时来自 [engine/valkyrie-cli](engine/valkyrie-cli)
- skill 自举脚本位于 [engine/scripts/run_skill_backend.py](engine/scripts/run_skill_backend.py)
- 如果 backend 被缓存到其他项目的 `.cache/lics/backend`，其运行时缓存仍应继续落在该缓存副本内部的 `.cache/` 下

## 工作目标

本仓库只做两件事：

1. 通过本地 Lucide 索引搜索图标，并在需要时下载单个 Lucide SVG。
2. 调用 `valkyrie-cli` 生成符合约束的 Jetpack Compose `ImageVector` Kotlin 源码。

## Skill 导向约束

- 优先把这个仓库视为 skill backend，而不是终端用户工具。
- skill 自举入口是 [engine/scripts/run_skill_backend.py](engine/scripts/run_skill_backend.py)。
- backend 执行入口是 `python -m engine.cli`。
- 如需刷新 Lucide 元数据索引，使用 `python -m engine.update_lucide_index`。
- 生成所需配置由调用方提供，backend 仓库不再提供默认 `config.json`。
- 如需手动调试，使用 `python -X pycache_prefix=.cache/pycache -m engine.cli ...`。
- 如果通过缓存 backend 执行 `generate`，需确认该 backend 自身也已包含 `engine/valkyrie-cli/`。

## 生成约束

- `target_dir` 必须是绝对路径。
- `package` 不能为空。
- `object_class_extension` 非空时，工作流必须先确保承载 `object` 文件存在。
- 如果承载文件已存在，其 `package` 与 `object` 声明都必须匹配配置。
- 若搜索结果不唯一，必须显式选择，不能静默猜测。
- `engine/valkyrie-cli/` 缺失时直接报错，不自动构建源码。
