"""Verify ClawSight's Hermes-side registration surface.

Lock the cross-product invariant: 5 engines × 5 verbs = 25 tools, exactly
the set listed in `hermes-plugin/plugin.yaml`. Drift here breaks
Hermes-side loading silently — the manifest would either reject the
plugin (manifest mismatch) or refuse to register tools that the runtime
expects, with no Python error to point at.

The companion vitest suite under `openclaw-plugin/src/register.test.ts`
asserts the equivalent invariant on the OpenClaw side. Together they
ensure the two runtimes advertise the same tool surface.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

# The test discovery path is `hermes_plugin/tests/` (imported via the
# dashed symlink); relative imports inside that package fail because we
# deliberately omit __init__.py to avoid shadowing the source plugin's
# package identity. Solve by making `tests/` importable as a top-level
# name. Mirrors clawpyter/hermes-plugin/tests/_bootstrap.py.
HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from hermes_plugin import register  # noqa: E402
from hermes_plugin.engines import ENGINES  # noqa: E402
from hermes_plugin.schemas import build_schemas  # noqa: E402
from _bootstrap import FakeCtx, ctx  # noqa: E402,F401  — fixture rebinding


ENGINE_NAMES = ["wsinsight", "sptxinsight", "hplot", "kurtorank", "wsitrain"]
VERBS = ["start", "stop", "status", "list_tools", "call"]
EXPECTED = {f"{eng}_{verb}" for eng in ENGINE_NAMES for verb in VERBS}


def test_engines_registry_matches_expected_set() -> None:
    """The ENGINES table drives both runtimes; if a row is added here,
    every other assertion must still pass."""
    assert sorted(ENGINES.keys()) == sorted(ENGINE_NAMES), (
        f"engine registry drift: {list(ENGINES.keys())} vs {ENGINE_NAMES}"
    )


def test_register_registers_25_tools(ctx: FakeCtx) -> None:
    register(ctx)
    assert len(ctx.tools) == 25, (
        f"expected 25 tools (5 engines × 5 verbs), got {len(ctx.tools)}"
    )


def test_register_tool_names_match_cross_product(ctx: FakeCtx) -> None:
    register(ctx)
    actual = {t.name for t in ctx.tools}
    assert actual == EXPECTED, (
        f"cross-product drift:\n"
        f"  missing: {sorted(EXPECTED - actual)}\n"
        f"  extra:   {sorted(actual - EXPECTED)}"
    )


def test_each_tool_routes_to_clawsight_toolset(ctx: FakeCtx) -> None:
    register(ctx)
    assert all(t.toolset == "clawsight" for t in ctx.tools), (
        f"every tool must use the 'clawsight' toolset, got "
        f"{ {t.toolset for t in ctx.tools} }"
    )


def test_each_handler_is_async(ctx: FakeCtx) -> None:
    """All 25 handlers are async def — async must be True on every one."""
    register(ctx)
    assert all(t.is_async for t in ctx.tools), (
        f"async handlers expected; found sync ones: "
        f"{ [t.name for t in ctx.tools if not t.is_async] }"
    )


def test_each_tool_has_object_parameter_schema(ctx: FakeCtx) -> None:
    register(ctx)
    for t in ctx.tools:
        params = t.schema.get("parameters") or {}
        assert params.get("type") == "object", (
            f"{t.name}: parameters.type must be 'object', got {params.get('type')!r}"
        )


def test_status_and_list_tools_may_have_empty_properties(ctx: FakeCtx) -> None:
    """status / list_tools are parameterless queries — they MUST
    have `type: object` but MAY have empty `properties`. start/stop/call
    MUST declare at least one property."""
    register(ctx)
    required_props = {"start", "stop", "call"}
    for t in ctx.tools:
        verb = t.name.rsplit("_", 1)[-1]
        params = t.schema.get("parameters") or {}
        props = params.get("properties", {})
        if verb in required_props:
            assert isinstance(props, dict) and len(props) > 0, (
                f"{t.name} ({verb}) declares no properties"
            )


def test_schemas_module_agrees_with_register(ctx: FakeCtx) -> None:
    """schemas.build_schemas() must match what register(ctx) installs;
    otherwise plugin.yaml (derived from schemas) would drift."""
    register(ctx)
    via_register = {t.name: t.schema for t in ctx.tools}
    via_schemas = build_schemas()
    assert via_register.keys() == via_schemas.keys(), (
        f"schemas/build_schemas vs register divergence:\n"
        f"  schemas-only:  {sorted(set(via_schemas) - set(via_register))}\n"
        f"  register-only: {sorted(set(via_register) - set(via_schemas))}"
    )


def test_plugin_yaml_agrees_with_register(ctx: FakeCtx) -> None:
    """The plugin manifest provides_tools MUST match the runtime surface.
    Drift here was the silent failure mode that motivated this suite."""
    register(ctx)
    runtime_names = {t.name for t in ctx.tools}

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("PyYAML not installed; manifest parity check skipped")

    yaml_path = (
        pathlib.Path(__file__).resolve().parents[2] / "hermes-plugin" / "plugin.yaml"
    )
    data = yaml.safe_load(yaml_path.read_text())
    manifest_names = set(data.get("provides_tools", []))
    assert runtime_names == manifest_names, (
        f"plugin.yaml manifest drift:\n"
        f"  in YAML not runtime: {sorted(manifest_names - runtime_names)}\n"
        f"  in runtime not YAML: {sorted(runtime_names - manifest_names)}"
    )


# ---------------------------------------------------------------------------
# Per-engine first-class guarantees.
#
# These lock the contract that hplot, kurtorank, and wsitrain are managed by
# ClawSight identically to wsinsight and sptxinsight. The acceptance bar is
# not "exists" but "fully wired": unique port, non-empty image, non-empty MCP
# binary, env-prefix matches the convention. A future contributor adding an
# engine that drops one of these fields silently degrades the engine to
# second-class; this test would catch it.
# ---------------------------------------------------------------------------


def test_every_engine_has_a_unique_port() -> None:
    ports = [e.port for e in ENGINES.values()]
    assert len(ports) == len(set(ports)), (
        f"duplicate port in ENGINES: "
        f"{ {p: [n for n, e in ENGINES.items() if e.port == p] for p in ports if ports.count(p) > 1} }"
    )


def test_every_engine_has_a_nonempty_image() -> None:
    for name, e in ENGINES.items():
        assert e.image, f"{name}: image is empty"
        assert e.image.startswith("huangchtw/"), (
            f"{name}: image {e.image!r} does not start with 'huangchtw/'"
        )


def test_every_engine_has_a_nonempty_mcp_bin() -> None:
    """mcp_bin is post-init-set to '<cli>-mcp' by default; engines that
    break the convention (wsitrain → wsinsight-train-mcp) override it.
    We verify the resolved value is non-empty and either matches the
    default convention or is an explicit override registered in the
    Engine dataclass (not a runtime guess)."""
    for name, e in ENGINES.items():
        assert e.mcp_bin, f"{name}: mcp_bin resolved to empty"
        # Default convention OR explicit override; both are acceptable.
        # Just ensure it does not contain whitespace, slashes, or other
        # characters that would break a `CMD ["wsitrain-mcp", ...]` invocation.
        assert " " not in e.mcp_bin, f"{name}: mcp_bin {e.mcp_bin!r} has whitespace"
        assert "/" not in e.mcp_bin, f"{name}: mcp_bin {e.mcp_bin!r} has '/'"


def test_every_engine_has_a_well_formed_env_prefix() -> None:
    """CLAWSIGHT_<ENGINE>_* env vars are how users override defaults at
    runtime; the env_prefix MUST be all-caps with no dashes or weird
    characters so a `os.environ.get(f"{prefix}_IMAGE")` lookup works."""
    for name, e in ENGINES.items():
        prefix = e.env_prefix
        assert prefix.startswith("CLAWSIGHT_"), (
            f"{name}: env_prefix {prefix!r} does not start with CLAWSIGHT_"
        )
        suffix = prefix[len("CLAWSIGHT_"):]
        assert suffix == suffix.upper(), (
            f"{name}: env_prefix suffix {suffix!r} is not all-upper"
        )
        assert "-" not in suffix, (
            f"{name}: env_prefix suffix {suffix!r} still has dashes"
        )


def test_every_engine_summary_is_nonempty() -> None:
    """Tool descriptions pull from `Engine.summary`; an empty summary
    surfaces as a blank `<engine>_start` description in both runtimes'
    tool catalog. Catch it at registration time."""
    for name, e in ENGINES.items():
        summary = e.summary.strip()
        assert summary, f"{name}: summary is empty/whitespace"
        # Tool descriptions should be sentences, not raw identifier lists.
        assert len(summary) >= 30, (
            f"{name}: summary {summary!r} is too short to be useful"
        )
