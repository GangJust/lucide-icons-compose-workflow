# Backend Contract

## Bootstrap Contract

This skill is no longer tied to one always-present workspace checkout.

Use `engine/scripts/run_skill_backend.py` as the primary entrypoint. It depends on `engine/scripts/resolve_backend.py` to locate or seed a backend copy.

The skill-level cache root is:

- Windows: `<workspace>\.cache\lics\backend`
- macOS / Linux: `<workspace>/.cache/lics/backend`

If a valid backend repo is found in the current workspace, the helper can use it directly when the workspace itself is the backend repo. Otherwise it seeds a project-local cached copy and reuses that copy afterward.

If no local backend can be found, the helper clones the default remote backend:

- `https://github.com/GangJust/lucide-icons-compose-skill`

The remote can be overridden with `--remote-url` or environment variable `LUCIDE_ICONS_COMPOSE_SKILL_REPO_URL`.

## Repo Contract

Treat the backend repository as the source of truth.

The repo root must contain:

- `SKILL.md`
- `engine/`
- `engine/cli.py`
- `engine/data/lucide-index.json`
- `engine/scripts/run_skill_backend.py`

For icon generation, the backend workspace should also have `engine/valkyrie-cli/` populated from an official Valkyrie release.
This runtime is not guaranteed to exist in a freshly cloned or cached backend copy unless it was unpacked there explicitly.

Do not bypass the backend with ad-hoc Lucide or Valkyrie calls unless the task is specifically to debug the backend implementation.

## Config Contract

Do not expect backend-root default config.
When generation is invoked through the skill helper, config must come from the caller project or an explicit `--config`.

Required fields:

- `target_dir`: absolute Kotlin source root
- `package`: output package name
- `object_class_extension`: optional carrier file name such as `Icons.kt`

Generation output must land in `target_dir + package path`, not merely `target_dir`.

The backend supports `--config <path>` or environment variable `LUCIDE_ICONS_COMPOSE_CONFIG`.

The skill helper additionally searches the current workspace and its ancestors for:

- `lucide-icons-compose.config.json`
- `.codex/lucide-icons-compose.json`
- `config.json` when it matches the config schema and is not the backend repo root

If none of these can be resolved during `generate`, the helper must stop with a clear error instead of silently using the backend repo's default config.

## Execution Contract

Prefer the skill helper:

- `python engine/scripts/run_skill_backend.py ...`

To force-refresh the cached backend from remote:

- `python engine/scripts/run_skill_backend.py --refresh-from-remote ...`

All skill-managed backend cache data should stay under the current project's `.cache/`, not under a global Codex directory.
When a cached backend copy is used, the backend root is typically `<workspace>/.cache/lics/backend`.

If debugging the backend directly, execute `python -m engine.cli ...` with `PYTHONPYCACHEPREFIX` set to repo `.cache/pycache`.

The helper itself must not leave repo-local `__pycache__` behind. All backend caches and temporary files stay under backend repo `.cache/`, including Python bytecode cache and temporary or cached SVG files. For a cached backend copy, that means paths such as `<workspace>/.cache/lics/backend/.cache/pycache`.
When multiple processes target the same cached backend, the seed or refresh phase must be serialized with `<workspace>/.cache/lics/backend.lock`.

Do not expect the backend repo to carry Valkyrie source code. Update the CLI by downloading a newer release from `https://github.com/ComposeGears/Valkyrie/releases` into `engine/valkyrie-cli/`.
If `generate` is invoked against a cached or freshly cloned backend without that runtime, the helper should stop with a clear error instead of deferring to a later backend failure.

Do not expect the backend repo to carry any Node.js MCP implementation for Lucide. Update Lucide metadata by running `python -m engine.update_lucide_index`.

## Icon Resolution Contract

Try exact icon `name` or `slug` first.

Use `search` and `categories` to narrow semantic queries.

If multiple candidates remain, require explicit disambiguation. Accept either:

- a clarified exact icon name or slug
- `generate ... --select N`

Do not silently choose one result from an ambiguous search.

## Carrier Object Contract

When `object_class_extension` is empty, generate top-level `val`.

When `object_class_extension` is non-empty:

- derive the object name from the file stem
- ensure the carrier file exists in the output package directory
- if missing, create the minimal file with the correct `package` and `object`
- if present but its `package` declaration is wrong, stop with an error
- if present but missing the expected `object` declaration, stop with an error

Do not expect Valkyrie to create the carrier object for you.
