"""Regenerate hermes-plugin/plugin.yaml's `provides_tools:` list.

The single source of truth is the engine registry in `engines.py` crossed with
the verbs in `tools.py`, so the manifest can never drift from the code.

Usage:
    python hermes-plugin/tools_sync.py --check   # exit 1 if drift
    python hermes-plugin/tools_sync.py           # rewrite plugin.yaml
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path

import yaml  # pyyaml ships in the hermes-agent runtime env.

HERE = Path(__file__).resolve().parent
PLUGIN_YAML = HERE / "plugin.yaml"

# The plugin directory is not importable by name (it contains a hyphen), so
# load its modules under a synthetic package to let relative imports resolve.
_PKG = "_clawsight_sync"


def _load_package() -> types.ModuleType:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(HERE)]
    sys.modules[_PKG] = pkg
    for mod in ("mcpclient", "engines", "schemas", "tools"):
        spec = importlib.util.spec_from_file_location(f"{_PKG}.{mod}", HERE / f"{mod}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{_PKG}.{mod}"] = module
        spec.loader.exec_module(module)
        setattr(pkg, mod, module)
    return pkg


def tool_names() -> list[str]:
    pkg = _load_package()
    names = sorted(pkg.schemas.build_schemas())
    handlers = sorted(pkg.tools.build_handlers())
    if names != handlers:
        raise SystemExit(f"schema/handler mismatch: {sorted(set(names) ^ set(handlers))}")
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 if plugin.yaml is out of sync instead of rewriting it.")
    args = ap.parse_args()

    names = tool_names()
    manifest = yaml.safe_load(PLUGIN_YAML.read_text(encoding="utf-8")) or {}
    current = manifest.get("provides_tools") or []

    if current == names:
        print(f"plugin.yaml is in sync ({len(names)} tools)")
        return 0

    if args.check:
        missing = sorted(set(names) - set(current))
        stale = sorted(set(current) - set(names))
        print("plugin.yaml is OUT OF SYNC")
        if missing:
            print("  missing:", ", ".join(missing))
        if stale:
            print("  stale  :", ", ".join(stale))
        return 1

    manifest["provides_tools"] = names
    PLUGIN_YAML.write_text(
        yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False,
                       allow_unicode=True, width=100),
        encoding="utf-8",
    )
    print(f"rewrote plugin.yaml with {len(names)} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
