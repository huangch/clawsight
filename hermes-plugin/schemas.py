"""JSON schemas for ClawSight tools, generated from the engine registry.

One template per verb; the engine's own metadata (GPU support, experimental
flag, summary) fills in the wording, so no schema is written by hand.
"""

from __future__ import annotations

from typing import Any

from .engines import ENGINES, Engine


def _start(e: Engine) -> dict[str, Any]:
    props: dict[str, Any] = {
        "data_dir": {
            "type": "string",
            "description": "Host directory mounted at /workspace inside the "
                           "container. All inputs and outputs live under it.",
        },
        "port": {
            "type": "integer",
            "description": f"Host/container port for the MCP server (default {e.port}).",
        },
        "container_name": {
            "type": "string",
            "description": f"Container name (default clawsight-{e.name}).",
        },
        "max_concurrent": {
            "type": "integer",
            "description": "Maximum concurrent jobs the server will run.",
        },
    }
    if e.gpu:
        props["gpu_ids"] = {
            "type": "string",
            "description": "Comma-separated GPU ids to expose, e.g. \"0,1\". "
                           "Empty or omitted exposes all GPUs.",
        }
    if e.experimental:
        props["experimental"] = {
            "type": "boolean",
            "description": "Expose experimental sub-commands as tools "
                           f"(default {str(e.experimental).lower()}).",
        }
    return {
        "type": "object",
        "description": (
            f"Start the {e.name} Docker container and its MCP server, then "
            f"discover the tools it exposes. {e.summary}"
        ),
        "properties": props,
        "required": ["data_dir"],
    }


def _stop(e: Engine) -> dict[str, Any]:
    return {
        "type": "object",
        "description": f"Stop and remove the {e.name} container.",
        "properties": {
            "container_name": {
                "type": "string",
                "description": f"Container name (default clawsight-{e.name}).",
            },
        },
        "required": [],
    }


def _status(e: Engine) -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            f"Report whether the {e.name} container is running, its MCP URL, "
            "and how many tools it currently exposes."
        ),
        "properties": {},
        "required": [],
    }


def _list_tools(e: Engine) -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            f"List the tools the running {e.name} server exposes, with a short "
            "description of each. Pass 'tool' to get one tool's full input "
            f"schema. Requires {e.name}_start to have been run."
        ),
        "properties": {
            "tool": {
                "type": "string",
                "description": "Return the full JSON input schema for this one "
                               "tool instead of the summary list.",
            },
        },
        "required": [],
    }


def _call(e: Engine) -> dict[str, Any]:
    return {
        "type": "object",
        "description": (
            f"Invoke any tool exposed by the running {e.name} server. Use "
            f"{e.name}_list_tools first to discover tool names and their "
            "parameters. Long-running tools return a job_id — poll it by "
            "calling this tool again with tool=\"job_status\"."
        ),
        "properties": {
            "tool": {
                "type": "string",
                "description": f"Tool name as reported by {e.name}_list_tools.",
            },
            "arguments": {
                "type": "object",
                "description": "Arguments object for that tool, matching its "
                               "input schema.",
            },
        },
        "required": ["tool"],
    }


TEMPLATES = {
    "start": _start,
    "stop": _stop,
    "status": _status,
    "list_tools": _list_tools,
    "call": _call,
}


def build_schemas() -> dict[str, dict[str, Any]]:
    """`{tool_name: tool_definition}` for every engine x verb combination.

    Hermes expects the OpenAI-style envelope — it reads properties from
    ``schema["parameters"]["properties"]`` (see tools/arg_coercion.py) — so the
    templates return the bare JSON Schema and it gets wrapped here.
    """
    out: dict[str, dict[str, Any]] = {}
    for name, engine in ENGINES.items():
        for verb, template in TEMPLATES.items():
            inner = template(engine)
            description = inner.pop("description", "")
            tool_name = f"{name}_{verb}"
            out[tool_name] = {
                "name": tool_name,
                "description": description,
                "parameters": inner,
            }
    return out


__all__ = ["build_schemas", "TEMPLATES"]
