---
name: lucide-icons-compose-skill
description: Search Lucide icons and generate Jetpack Compose ImageVector Kotlin source through a self-bootstrapping lucide-icons-compose-skill backend. Use when Codex needs to add or update Lucide-based Compose icons, search Lucide icon names or categories, run generation from any workspace, honor caller-provided config, create or validate an object_class_extension carrier file, or disambiguate multiple icon candidates before generation.
---

# Lucide Icons Compose Skill

Use the helper scripts in this skill instead of manually stitching together Lucide search and Valkyrie conversion steps.

## Bootstrap The Backend

Run `engine/scripts/run_skill_backend.py` from this skill whenever possible. It locates a matching backend repo, seeds a cached copy into the current workspace `.cache/lics/backend`, and then runs the backend implementation from that project-local cache.

If the current project cache already exists, the skill reuses it before doing any backend bootstrap work.

The helper itself does not write repo-local `__pycache__`. Backend bytecode and temporary files stay under the resolved backend `.cache/`, which is still inside the caller project's `.cache/` subtree when a cached backend copy is used.
When multiple processes try to seed or refresh the same cached backend, the helper serializes that step with `<workspace>/.cache/lics/backend.lock`.

The helper looks for a repository root that contains all of:

- `SKILL.md`
- `engine/`
- `engine/cli.py`
- `engine/data/lucide-index.json`
- `engine/scripts/run_skill_backend.py`

For `generate`, the backend root should additionally provide `engine/valkyrie-cli/` with the official release CLI unpacked inside `engine/`.

If the backend was cloned from remote or restored from a project cache, do not assume `engine/valkyrie-cli/` is already present. Seed from a local checkout that already contains the runtime, or unpack the official release into the resolved backend before running `generate`.

Lookup order:

- `--backend-path`
- environment variable `LUCIDE_ICONS_COMPOSE_SKILL_BACKEND`
- current working directory and its ancestors
- cached backend under `<workspace>/.cache/lics/backend`
- clone from default remote `https://github.com/GangJust/lucide-icons-compose-skill`

Remote override options:

- `--remote-url`
- environment variable `LUCIDE_ICONS_COMPOSE_SKILL_REPO_URL`

If the backend implementation changes later and you want to refresh the cached copy, run the helper once with `--refresh-from-remote`, or reseed the current project cache from a local checkout with `--backend-path <repo-root>`.

For the full bootstrap and backend contract, read [references/backend-contract.md](references/backend-contract.md).

## Use The Backend Entry Point

Do not expect the backend repo to provide a default `config.json`.
For `generate`, always use caller-provided config discovery or an explicit `--config`.

Auto-discovery order for generation is:

- explicit `--config`
- environment variable `LUCIDE_ICONS_COMPOSE_CONFIG`
- `lucide-icons-compose.config.json` in the current workspace or its ancestors
- `.codex/lucide-icons-compose.json` in the current workspace or its ancestors
- `config.json` in the current workspace or its ancestors, but only when it matches the config schema and is not the backend repo root

If no project config can be resolved, stop and ask the user to provide `--config` or add one of the project config files above. Do not silently fall back to the backend repo's own default config for cross-project generation.

Preferred helper invocations:

- `python engine/scripts/run_skill_backend.py categories`
- `python engine/scripts/run_skill_backend.py search arrow left`
- `python engine/scripts/run_skill_backend.py generate arrow-left`
- `python engine/scripts/run_skill_backend.py generate arrow --select 2`
- `python engine/scripts/run_skill_backend.py generate arrow-left --config D:\path\to\config.json`

Use the backend repo directly only when debugging the backend implementation. In that case prefer `python -m engine.cli ...`.

## Resolve Icons Safely

Try exact `name` or `slug` first.

If the user gives a semantic query, use `search` or `categories` to narrow candidates before generation.

If search returns one candidate, use it directly. If search returns multiple candidates, require explicit selection or pass `--select N`. Do not silently guess.

Do not bypass the backend's local Lucide index or upstream Lucide sources with ad-hoc SVG from other sources unless the user explicitly asks to debug or replace the backend.

## Generate And Verify

Run `generate` through `engine/scripts/run_skill_backend.py`.

After generation, verify the generated Kotlin file:

- lands under `target_dir + package path`
- has the configured `package` declaration
- uses an extension property like `val Icons.ArrowLeft: ImageVector` when `object_class_extension` is non-empty

If `object_class_extension` is configured, ensure the carrier Kotlin file exists or let the backend create the minimal `object` file. If the file exists but does not declare the expected object, stop and surface the mismatch instead of guessing.
If the file exists but its `package` declaration does not match config, stop and surface the mismatch instead of guessing.
