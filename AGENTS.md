# AGENTS.md — ClawSight

Standing instructions for AI agents (Hermes, Claude Code, Codex, …) working **in this repository**. This file is for *developing* ClawSight; it is not part of the plugin packaging shipped to end users.

## What this repo is

ClawSight gives AI agents control over the WSInsight family of compute engines
through Docker-hosted MCP servers. Five engines ship today
([`engines.ts`](openclaw-plugin/src/engines.ts) / [`engines.py`](hermes-plugin/engines.py)):

| Engine | Default port | GPU | Image |
|---|---|---|---|
| `wsinsight` | 8765 | yes | `huangchtw/wsinsight` |
| `sptxinsight` | 8766 | yes | `huangchtw/sptxinsight` |
| `hplot` | 8767 | no | `huangchtw/hplot` |
| `kurtorank` | 8768 | no | `huangchtw/kurtorank` |
| `wsitrain` | 8769 | yes | `huangchtw/wsitrain` |

Each engine exposes the same five tools — `<engine>_start`, `_stop`,
`_status`, `_list_tools`, `_call` — on both runtimes. Tool catalogs are
**discovered at runtime** from the running container; nothing is hard-coded.

## Engines are the single source of truth

**Adding a new engine touches exactly one row per runtime:**

- Hermes: `hermes-plugin/engines.py :: ENGINES` + `mcp_bin` if the MCP binary
  is not `<cli>-mcp`.
- OpenClaw: `openclaw-plugin/src/engines.ts :: ENGINES`.

After changing either, regenerate the schema/handler pair on Hermes:

```bash
python hermes-plugin/tools_sync.py            # rewrite plugin.yaml
python hermes-plugin/tools_sync.py --check    # exit 1 on drift
```

`buildTools()` (OpenClaw) and `schemas.build_schemas()` (Hermes) cross-product
the registry with the verb templates — no engine-specific schema or handler
code lives anywhere else in the repos.

## Tools are cross-products, not sub-commands

The plugin exposes container **lifecycle** + a generic call proxy. The actual
pipeline sub-commands (`run`, `infer`, `screen`, `niche`, …) live **inside the
container's MCP server** and are surfaced via `<engine>_list_tools` +
`<engine>_call`. Resist the urge to hand-write per-subcommand tools in this
plugin — that duplicates the schema the container already advertises, and
drifts the moment the CLI changes.

## SKILL.md sync rule (important)

`hermes-plugin/SKILL.md` and `openclaw-plugin/skills/clawsight/SKILL.md` MUST
stay in sync. They describe the same surface to the agent and serve as the
authoritative user docs. When editing one, mirror the change in the other —
both must agree on tool names, parameter vocabulary, and lifecycle guidance.

`README.md` §Installation and §Development mirror the same surface and must
also be updated whenever either side drifts.

## Build / deploy

```sh
# Hermes side: install plugin into the agent's plugins dir.
./build4hermes.sh           # pip deps + copy hermes-plugin/ -> ~/.hermes/plugins/clawsight/

# OpenClaw side: type-check, test, build, install.
cd openclaw-plugin
npm install                 # vitest + typebox + typescript
npx vitest run              # 6 tests
npx tsc -p tsconfig.json --noEmit    # type-check
npx tsc -p tsconfig.json            # build dist/
cd ..
./build4openclaw.sh         # uninstall-before-install; running OpenClaw daemon may need `openclaw daemon restart`
```

## Tests (Hermes plugin Python suite)

The Hermes registration surface is exercised by a sync pytest suite under
`hermes-plugin/tests/` (9 tests as of Sep-2026). It locks the
cross-product invariant (5 engines × 5 verbs = 25 tools), the manifest
parity against `plugin.yaml`, and the schema/build_schemas agreement.
Tests use the canonical Python module name `hermes_plugin` via a dev-only
symlink so Python's import system can resolve the directory — the
source-of-truth path `hermes-plugin/` has a dash, which Python
identifiers cannot use.

```sh
# One-time: create the dev-only import alias (gitignored).
ln -sf hermes-plugin hermes_plugin

# Run:
python3 -m pytest                       # uses pytest.ini testpaths = hermes_plugin/tests
python3 -m pytest -v                    # verbose
python3 -m pytest -k cross_product       # narrow via -k filter
```

CI is local today; add `python3 -m pytest hermes_plugin/tests/` to the
dev workflow if you wire CI later.

## Tests (OpenClaw plugin TypeScript suite)

The OpenClaw plugin (`openclaw-plugin/`) ships a parallel TypeScript suite
run by **vitest** (6 tests as of Sep-2026). It mirrors the Python suite:

- `register.test.ts` exercises the cross-product invariant — 5 engines ×
  5 verbs = exactly 25 tools register, every tool name falls inside the
  expected set, every tool advertises `parameters.type === "object"` and
  start/stop/call declare at least one property (status / list_tools may
  have empty `properties`), and every executor wraps its return in
  `{ content: [{ type: "text", text: "…" }] }`.

Run:

```sh
cd openclaw-plugin
npm install                                   # installs vitest + typebox
npx vitest run                                # 6 tests in <1s
npx vitest run src/register.test.ts            # narrow by path
```

`vitest.config.ts` resolves the bare specifier
`openclaw/plugin-sdk/plugin-entry` (the OpenClaw host's plugin SDK, not
installed here as a direct dep) to a test-only stub at
`src/test-stub-openclaw-sdk.ts`. The stub mirrors the minimum API our
`index.ts` uses (`definePluginEntry` + `OpenClawPluginApi`) so the
plugin's `register(api)` can be exercised without standing up the host.
Test files (`*.test.ts`, `test-utils.ts`, `test-stub-*.ts`) are excluded
from the production `tsc -p tsconfig.json` build via the `exclude` list.

## Defining the entry point

The OpenClaw plugin uses the `definePluginEntry({...})` shape introduced
in OpenClaw 2026.9.x — NOT the legacy `export default function
register(api: any)` shape. The legacy shape still loads, but:

- `api: any` defeats `tsc`'s typechecker;
- `definePluginEntry` carries the typed `configSchema`, future-capable
  `kind` / `reload` / `securityAuditCollectors` slots, and matches the
  pattern clawpyter adopted in 2026-09.

If you ever need the bare `register(api)` shape for a stub or a
non-OpenClaw host, import `OpenClawPluginApi` from the SDK ambient
declaration at `src/types/openclaw-sdk.d.ts` — that's the typed shape
the host will hand in via `api.pluginConfig` etc.

## Conventions

- Both runtimes read per-engine defaults from `CLAWSIGHT_<ENGINE>_*` env vars
  (`IMAGE`, `PORT`, `CONTAINER`, `MCP_URL`, `TIMEOUT_MS`); `<ENGINE>` is upper-
  cased, dashes → underscores. Mirror this in any new shell helper.
- `_start` passes `HOST_UID`/`HOST_GID` into the container, which remaps the
  baked-in `user` (uid 1000). The OpenClaw plugin guards `process.getuid()` /
  `process.getgid()` with a narrowing cast (`posixIds`) because they don't
  exist on Windows; keep that guard if you touch the start path.
- The OpenClaw `package.json` declares `pluginApi: ">=2026.3.24-beta.2"` — the
  date-based semver format is enforced by OpenClaw's manifest validator
  (see [openclaw/docs/plugins/sdk-setup.md](../openclaw/docs/plugins/sdk-setup.md)).
- The OpenClaw plugin is an ESM project (`"type": "module"`); use
  `await import("…")` for dynamic loads (e.g. optional deps), not `require`.
- `registerTool` always lives behind a defensive null check — OpenClaw plugins
  load before their SDK is ready, so guard the API surface and emit a clear
  warning instead of crashing.
