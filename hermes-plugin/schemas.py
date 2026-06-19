"""LLM-visible JSON schemas for the 15 ClawSight tools."""

# Pipeline tools share a single free-form 'arguments' field.
# The agent calls wsinsight_list_tools first to learn exact parameter names
# from the live MCP server, then fills in 'arguments' accordingly.
_ARGS_PROPERTY = {
    "arguments": {
        "type": "object",
        "description": (
            "Arguments for this WSInsight command as a JSON object. "
            "Call wsinsight_list_tools first to discover the exact parameter "
            "names, types, and required fields for this command."
        ),
        "additionalProperties": True,
    }
}

# ---------------------------------------------------------------------------
# Connection / Docker management
# ---------------------------------------------------------------------------

WSINSIGHT_SERVER_INFO = {
    "name": "wsinsight_server_info",
    "description": (
        "Return the current ClawSight configuration: MCP endpoint URL, "
        "Docker container name, request timeout, and whether a session is "
        "active. Use this to verify the plugin state before running pipelines."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

WSINSIGHT_CONNECT = {
    "name": "wsinsight_connect",
    "description": (
        "Connect to a running WSInsight MCP server and verify it is reachable. "
        "Performs the MCP initialize handshake and returns the server name, "
        "version, and protocol version on success. "
        "Optionally override the MCP URL or timeout without restarting the plugin."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mcp_url": {
                "type": "string",
                "description": (
                    "MCP endpoint URL (e.g. http://127.0.0.1:8765/mcp). "
                    "Overrides the current URL for this and all future calls."
                ),
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Request timeout in milliseconds (default: 300000).",
                "minimum": 1000,
            },
        },
        "required": [],
    },
}

WSINSIGHT_START_DOCKER = {
    "name": "wsinsight_start_docker",
    "description": (
        "Start the WSInsight Docker container (huangchtw/wsinsight:latest) "
        "with the MCP HTTP server listening inside. "
        "data_dir is mounted read-write as /workspace — all file paths passed "
        "to pipeline tools must be relative to that mount. "
        "Any previously running container with the same name is stopped first. "
        "Returns the container ID and MCP URL on success; wait ~5 s then call "
        "wsinsight_connect to verify."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data_dir": {
                "type": "string",
                "description": (
                    "Absolute host path mounted as /workspace inside the "
                    "container. All WSI paths in pipeline calls are relative "
                    "to this directory. Required."
                ),
            },
            "gpu_ids": {
                "type": "string",
                "description": (
                    "Comma-separated GPU device IDs to expose "
                    "(e.g. '0' or '0,1'). Default: all GPUs."
                ),
            },
            "mcp_port": {
                "type": "integer",
                "description": "Host port to bind the MCP server to. Default: 8765.",
                "minimum": 1024,
                "maximum": 65535,
            },
            "container_name": {
                "type": "string",
                "description": "Docker container name. Default: clawsight-mcp.",
            },
            "max_concurrent": {
                "type": "integer",
                "description": (
                    "Maximum concurrent GPU jobs inside the container. "
                    "Default: auto (= number of exposed GPUs)."
                ),
                "minimum": 1,
            },
            "experimental": {
                "type": "boolean",
                "description": (
                    "Expose experimental WSInsight tools "
                    "(hplot, hplot-finalize, ecomp, tcomp, cme, cme-profile). Default: false."
                ),
            },
        },
        "required": ["data_dir"],
    },
}

WSINSIGHT_STOP_DOCKER = {
    "name": "wsinsight_stop_docker",
    "description": (
        "Stop and remove the WSInsight MCP Docker container. "
        "All running jobs inside will be terminated."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "container_name": {
                "type": "string",
                "description": "Name of the container to stop. Default: clawsight-mcp.",
            },
        },
        "required": [],
    },
}

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

WSINSIGHT_LIST_TOOLS = {
    "name": "wsinsight_list_tools",
    "description": (
        "List all tools currently available on the WSInsight MCP server, "
        "including their parameter names, types, and required fields. "
        "Always call this before using pipeline tools so you know exactly "
        "what to put in the 'arguments' object."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

# ---------------------------------------------------------------------------
# Pipeline tools
# ---------------------------------------------------------------------------

WSINSIGHT_RUN = {
    "name": "wsinsight_run",
    "description": (
        "Run the full WSInsight end-to-end pipeline on a WSI: "
        "tissue segmentation → patch extraction → GPU model inference → "
        "per-cell neighborhood composition → export. "
        "Returns a job_id immediately; poll wsinsight_job_status for progress. "
        "File paths in 'arguments' must be relative to /workspace (= data_dir). "
        "Call wsinsight_list_tools to discover the exact parameter names."
    ),
    "parameters": {
        "type": "object",
        "properties": _ARGS_PROPERTY,
        "required": ["arguments"],
    },
}

WSINSIGHT_PATCH = {
    "name": "wsinsight_patch",
    "description": (
        "Segment tissue regions and extract patches from a WSI into an HDF5 cache. "
        "Returns a job_id immediately; poll wsinsight_job_status for progress. "
        "Call wsinsight_list_tools to discover the exact parameter names."
    ),
    "parameters": {
        "type": "object",
        "properties": _ARGS_PROPERTY,
        "required": ["arguments"],
    },
}

WSINSIGHT_INFER = {
    "name": "wsinsight_infer",
    "description": (
        "Run GPU model inference on pre-extracted patches. "
        "Requires a prior wsinsight_patch run for the same WSI. "
        "Returns a job_id immediately; poll wsinsight_job_status for progress. "
        "Call wsinsight_list_tools to discover the exact parameter names."
    ),
    "parameters": {
        "type": "object",
        "properties": _ARGS_PROPERTY,
        "required": ["arguments"],
    },
}

WSINSIGHT_NCOMP = {
    "name": "wsinsight_ncomp",
    "description": (
        "Compute per-cell neighborhood composition on a Delaunay graph "
        "from inference results. "
        "Requires a prior wsinsight_infer run. "
        "Returns a job_id immediately; poll wsinsight_job_status for progress. "
        "Call wsinsight_list_tools to discover the exact parameter names."
    ),
    "parameters": {
        "type": "object",
        "properties": _ARGS_PROPERTY,
        "required": ["arguments"],
    },
}

WSINSIGHT_EXPORT = {
    "name": "wsinsight_export",
    "description": (
        "Export inference or composition results to GeoJSON or OME-CSV. "
        "Runs synchronously and returns the exit status and a log tail. "
        "Call wsinsight_list_tools to discover the exact parameter names."
    ),
    "parameters": {
        "type": "object",
        "properties": _ARGS_PROPERTY,
        "required": ["arguments"],
    },
}

WSINSIGHT_REG = {
    "name": "wsinsight_reg",
    "description": (
        "Register (spatially align) two WSI regions. "
        "Runs synchronously and returns the exit status and a log tail. "
        "Call wsinsight_list_tools to discover the exact parameter names."
    ),
    "parameters": {
        "type": "object",
        "properties": _ARGS_PROPERTY,
        "required": ["arguments"],
    },
}

# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------

WSINSIGHT_JOB_STATUS = {
    "name": "wsinsight_job_status",
    "description": (
        "Poll the status of a background WSInsight job. "
        "Returns: job_id, status (pending / running / done / error / cancelled), "
        "start time, elapsed time, and a short progress snippet from the log. "
        "Call this repeatedly after a pipeline tool until status is 'done' or 'error'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID returned by a pipeline tool (run, patch, infer, ncomp).",
            },
        },
        "required": ["job_id"],
    },
}

WSINSIGHT_JOB_LOGS = {
    "name": "wsinsight_job_logs",
    "description": (
        "Retrieve the last N stdout/stderr log lines from a background job. "
        "Use this to inspect progress output or diagnose errors."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID returned by a pipeline tool.",
            },
            "tail": {
                "type": "integer",
                "description": "Number of log lines to return (default: 50).",
                "minimum": 1,
                "maximum": 4000,
            },
        },
        "required": ["job_id"],
    },
}

WSINSIGHT_CANCEL_JOB = {
    "name": "wsinsight_cancel_job",
    "description": "Cancel a running or pending WSInsight background job by job_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "description": "Job ID to cancel.",
            },
        },
        "required": ["job_id"],
    },
}

WSINSIGHT_LIST_JOBS = {
    "name": "wsinsight_list_jobs",
    "description": (
        "List all WSInsight background jobs (running, pending, done, error, cancelled) "
        "with their job_id, command name, status, and elapsed time."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}
