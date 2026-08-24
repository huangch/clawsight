"""Regenerate hermes-plugin/plugin.yaml's `provides_tools:` list from `__init__.py`.

Single source of truth lives in the `_TOOLS` tuple in `__init__.py` — every
`ctx.register_tool(name=...)` call is enumerated via AST so we never have to
hand-sync the YAML list again.

Usage:
    /opt/anaconda3/envs/wsi/bin/python hermes-plugin/tools_sync.py --check   # exit 1 if drift
    /opt/anaconda3/envs/wsi/bin/python hermes-plugin/tools_sync.py            # rewrite plugin.yaml
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import yaml  # pyyaml ships in the hermes-agent runtime env.

HERE = Path(__file__).resolve().parent
INIT_PY = HERE / "__init__.py"
PLUGIN_YAML = HERE / "plugin.yaml"


def _tools_from_init() -> list[str]:
    """Pull canonical tool names from the `_TOOLS` tuple in `__init__.py`."""
    tree = ast.parse(INIT_PY.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        # Each entry is a 2/3-tuple `(name, schema, [handler])` — name is a str
        # literal that starts with `wsinsight_` or `sptx_`.
        if isinstance(node, ast.Tuple) and len(node.elts) >= 2:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                t = first.value
                if t.startswith(("wsinsight_", "sptx_")):
                    out.append(t)
    return out


def _yaml_provides_tools() -> list[str] | None:
    """Pull `provides_tools:` list from `plugin.yaml`."""
    data = yaml.safe_load(PLUGIN_YAML.read_text())
    return list(data.get("provides_tools", []))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if plugin.yaml drift detected, do not rewrite.",
    )
    args = ap.parse_args(argv)

    canonical = _tools_from_init()
    yaml_list = _yaml_provides_tools() or []

    if set(canonical) == set(yaml_list):
        print(f"OK — both lists contain {len(canonical)} tools.")
        return 0
    if args.check:
        only_code = sorted(set(canonical) - set(yaml_list))
        only_yaml = sorted(set(yaml_list) - set(canonical))
        print(f"DRIFT: in code but not yaml: {only_yaml}")
        print(f"DRIFT: in yaml but not code: {only_code}", file=sys.stderr)
        return 1

    canon = yaml.safe_load(PLUGIN_YAML.read_text())
    canon["provides_tools"] = sorted(canonical)
    PLUGIN_YAML.write_text(
        yaml.safe_dump(canon, sort_keys=False, default_flow_style=False, allow_unicode=True)
    )
    print(f"Rewritten {PLUGIN_YAML} with {len(canonical)} tools.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
