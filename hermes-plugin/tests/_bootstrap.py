"""Hermes-side test bootstrap for ClawSight.

Mirrors clawpyter/hermes-plugin/tests/_bootstrap.py:
* pytest.ini declares testpaths = hermes_plugin/tests so the only pytest
  invocation needed is `python3 -m pytest`.
* No pytest-asyncio dependency; the synchronous `register(ctx)` body is
  exercised via a fake PluginContext that captures every tool registration
  and lets us inspect the captured toolset.
* The cross-product invariant — 5 engines × 5 verbs = 25 tools — is the
  single most important contract ClawSight has. Drift between the engine
  registry (engines.py), the schema builder (schemas.build_schemas), and
  the plugin.yaml manifest breaks Hermes-side loading without warning; we
  lock it here.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any, Callable

import pytest


# The source-of-truth directory is `hermes-plugin/` (dash in the name),
# which Python cannot import directly. The dev-only symlink `hermes_plugin`
# (created by AGENTS.md / README) is the canonical module path. Tests
# assume that symlink is in place.
HERE = pathlib.Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent  # hermes-plugin/
REPO_ROOT = PLUGIN_ROOT.parent  # clawsight/
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# CapturedTool + FakeCtx — mirrors clawpyter's parallel harness.
# ---------------------------------------------------------------------------

class CapturedTool:
    """One captured register_tool(name, toolset, schema, handler, is_async)
    call. The handler is invoked directly by tests via `await captured.invoke(...)`
    in async tests, but the contract under test here is *registration*, not
    handler execution; we only need the metadata."""

    __slots__ = ("name", "toolset", "schema", "handler", "is_async")

    def __init__(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        is_async: bool,
    ) -> None:
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.is_async = is_async


class FakeCtx:
    """Minimal PluginContext stand-in.

    The real PluginContext (hermes-agent/hermes_cli/plugins.py:449) accepts
    (name, toolset, schema, handler, check_fn=None, requires_env=None,
    is_async=False, ...). We capture the four canonical args and `is_async`
    so we can verify that handlers registered as async.
    """

    def __init__(self) -> None:
        self.tools: list[CapturedTool] = []

    def register_tool(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Callable | None = None,
        requires_env: list | None = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        override: bool = False,
        **_extra: Any,
    ) -> None:
        self.tools.append(
            CapturedTool(
                name=name,
                toolset=toolset,
                schema=schema,
                handler=handler,
                is_async=is_async,
            )
        )


@pytest.fixture
def ctx() -> FakeCtx:
    return FakeCtx()
