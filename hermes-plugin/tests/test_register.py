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
