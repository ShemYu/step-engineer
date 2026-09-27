# Build a Step worker into your own CLI or MCP

[English README](../README.md) · [繁體中文](README.zh-TW.md) · [Delegation instructions](parent-agent-instructions.md)

Step Engineer is a reusable harness specifically for **Step-5-Preview**. Developers can use its existing CLI/MCP server or wrap its Python components in their own tools. GPT, Grok, or Claude acts as the orchestrator: it defines a bounded task, delegates the measurable iteration to Step, and reviews the result. The worker is designed for explicit constraints and repeated check–measure–improve cycles; its suitability still needs validation on your workload.

The parent model, authentication, conversation loop, and reasoning settings stay in the host application. A job's `reasoning_effort` controls only Step and defaults to `medium`; Ultra, when available, remains a parent setting.

Before exposing a domain-specific shortcut, define its [task contract](task-brief.md):
environment, editable policy, objective, hard constraints, permitted tradeoffs,
and final checks. The [use-case guide](use-cases.md) identifies suitable work.
The [resource-allocation example](../examples/resource_allocation/README.md)
shows how a fixed evaluator and an editable policy fit the existing `JobSpec`;
the CLI and MCP submission schema are unchanged.

```text
GPT / Grok / Claude orchestrator
  -> Your CLI, MCP host, or API tool executor
  -> Step Engineer harness -> Step-5-Preview + isolated local checks
  -> Measured best candidate and final-validation evidence
  -> Orchestrator review; original source remains unchanged
```

Every `/absolute/path/to/...` below is a placeholder. Use paths appropriate to your installation; do not paste credential values into client configuration or prompts.

## Verify the CLI first

From the repository root:

```sh
uv sync --frozen --python 3.12
uv run step-engineer schema
uv run step-engineer --runs-dir ./runs run examples/batch_aggregation/job.json --offline-demo
uv run step-engineer --runs-dir ./runs report RUN_ID
```

Replace `RUN_ID` with the returned identifier. The offline demo uses a handwritten answer and makes no model request. It tests the harness, not Step's performance.

For a live worker, provide `STEP_API_KEY` or fallback `STEPFUN_API_KEY` in the process environment, or explicitly load a private dotenv file. The CLI does not implicitly search for credential files.

```sh
uv run step-engineer --env-file /absolute/path/to/private/step.env doctor
uv run step-engineer --env-file /absolute/path/to/private/step.env \
  --runs-dir ./runs run examples/batch_aggregation/job.json
```

Global options such as `--env-file` and `--runs-dir` go **before** `run`, `serve`, or `report`. `doctor` is a local presence check, not an authentication or quota check. The model is `step-5-preview`; there is no `STEP_MODEL` environment switch.

## Local MCP stdio

Have your MCP client launch and manage this process:

```sh
uv run --project /absolute/path/to/step-engineer step-engineer \
  --env-file /absolute/path/to/private/step.env \
  --runs-dir /absolute/path/to/optimization-runs \
  serve --allow-root /absolute/path/to/your-project
```

No HTTP server is exposed. Repeat `--allow-root` for additional authorized projects. Keep the process/session alive until the job finishes; closing it cancels active work.

| Tool | Arguments | Behavior |
| --- | --- | --- |
| `submit_optimization` | `job: object` | Validates the job and returns a queued run ID |
| `get_optimization_status` | `run_id: string` | Reads progress and estimated cost |
| `get_optimization_result` | `run_id: string` | Reads results and local artifact paths |
| `cancel_optimization` | `run_id: string` | Cancels the local task; an API request may already be billable |

Use an **absolute** `job.source_dir` with MCP. CLI relative paths are resolved beside the job JSON, but an MCP call has no job-file location. Poll status at reasonable intervals, then fetch the result even if the job failed or hit a limit. A result is not an instruction to deploy or merge.

### Codex configuration example

Add a stdio server entry in the applicable Codex MCP configuration, following the [official MCP guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli):

```toml
[mcp_servers.step_engineer]
command = "/absolute/path/to/uv"
args = ["run", "--project", "/absolute/path/to/step-engineer", "step-engineer", "--env-file", "/absolute/path/to/private/step.env", "--runs-dir", "/absolute/path/to/optimization-runs", "serve", "--allow-root", "/absolute/path/to/your-project"]
startup_timeout_sec = 30
tool_timeout_sec = 60
```

This references a local credential file without embedding a key. Alternatively, remove the two `--env-file` arguments and arrange for the server process to inherit `STEP_API_KEY`. Reload the MCP client configuration as required by that client. Do not change the parent's model or reasoning setting to configure this worker.

### Claude Code configuration example

A Claude Code MCP config can launch the same process. See the [official MCP guide](https://code.claude.com/docs/en/mcp).

```json
{
  "mcpServers": {
    "step_engineer": {
      "type": "stdio",
      "command": "/absolute/path/to/uv",
      "args": ["run", "--project", "/absolute/path/to/step-engineer", "step-engineer", "--env-file", "/absolute/path/to/private/step.env", "--runs-dir", "/absolute/path/to/optimization-runs", "serve", "--allow-root", "/absolute/path/to/your-project"]
    }
  }
}
```

For a config saved at a chosen path, launch the client with its supported config option, for example `claude --mcp-config /absolute/path/to/step-mcp.json`. No global registration is required by Step Engineer itself.

## Build your own CLI or MCP

There is no scaffold-generator command. These importable components are the current extension surface:

| Component | Your wrapper owns | Existing behavior you reuse |
| --- | --- | --- |
| `JobSpec` and `load_job(path)` | Objective, file list, checks, metrics, budget, task templates | Validation and CLI-relative source resolution |
| `JobService(runs_dir, allowed_roots)` | Authorized roots, artifact location, process lifetime | Async jobs, status/results, cancellation; at most two active jobs |
| `build_server(service)` | MCP launcher and optional domain-specific tools | Four standard tools and shutdown cleanup |
| `ToolBridge(service)` | Parent API client and tool-result envelopes | Provider-shaped schemas and local dispatch |
| `Harness(spec, run_dir, client)` | Lower-level runner integration | Step tool loop, measurements, best snapshot, final verification |

Prefer `JobService` in a wrapper: it applies source-root authorization and creates run directories. Direct `Harness` construction does **not** add those service-level policies for you. The current harness is an engineering optimizer with a fixed set of worker tools; it does not provide a general plugin registry, model router, or arbitrary workflow generator. New checks and workloads usually belong in a `JobSpec`; changing the worker tool set or execution backend requires implementation work.

### A custom Python CLI

Save this as `optimize_cli.py` in your own tooling project, with `step_engineer` installed in its environment. It reuses the same job contract and keeps the event loop alive until termination. An existing Step key is required for live mode; `--offline-demo` only accepts the bundled example and makes no model request.

```python
import argparse
import asyncio
import json
import sys
from pathlib import Path

from step_engineer.cli import load_job
from step_engineer.service import JobService


async def optimize(args):
    job = load_job(args.job)
    service = JobService(
        args.runs_dir, [args.allow_root], offline_demo=args.offline_demo
    )
    try:
        async with asyncio.timeout(job.budget.max_seconds + 120):
            submitted = await service.submit(job)
            run_id = submitted["run_id"]
            print(json.dumps({"run_id": run_id}), file=sys.stderr, flush=True)
            while service.status(run_id)["status"] in {"queued", "running"}:
                await asyncio.sleep(5)
            return service.result(run_id)
    finally:
        # Also cancels outstanding work if this CLI is interrupted or times out.
        await service.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path)
    parser.add_argument("--allow-root", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--offline-demo", action="store_true")
    args = parser.parse_args()
    try:
        result = asyncio.run(optimize(args))
    except KeyboardInterrupt:
        return 130
    except Exception:
        # Do not echo errors that may include job contents or provider details.
        print('{"error":"Local optimization failed or timed out"}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

For example, from an environment with the package installed:

```sh
python optimize_cli.py /absolute/path/to/job.json \
  --allow-root /absolute/path/to/your-project \
  --runs-dir /absolute/path/to/optimization-runs
```

Relative `source_dir` still resolves beside the job JSON. This wrapper exits successfully only for an accepted improvement; the built-in CLI has its own exit-code behavior. Neither applies the patch. A keyless smoke check can add `--offline-demo` while pointing both the job and allowed root at the bundled example. Raw result JSON can contain project-specific details; do not publish it without review.

### A custom MCP launcher and task shortcut

Save this as `optimization_mcp.py`. It adds a shortcut that submits a developer-selected job file while retaining the four standard tools for status, results, cancellation, and general submission.

```python
import argparse
from pathlib import Path

from step_engineer.cli import load_job
from step_engineer.server import build_server
from step_engineer.service import JobService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", type=Path)
    parser.add_argument("--allow-root", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    args = parser.parse_args()
    service = JobService(args.runs_dir, [args.allow_root])
    server = build_server(service)

    @server.tool()
    async def optimize_reviewed_job() -> dict:
        """Submit this launcher's reviewed job; returns a run ID, not a patch."""
        return await service.submit(load_job(args.job))

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
```

Configure your MCP host to launch this Python script with the job, `--allow-root`, and `--runs-dir` arguments. Provision the Step key in that process environment. `build_server` owns the service's shutdown lifecycle and calls `await service.close()` when the session ends; do not close the service after each tool call. Inside an already-running async host, use its existing event loop for service/bridge calls rather than nesting `asyncio.run()`.

The shortcut is a convenience, **not an access restriction**: `build_server` still exposes `submit_optimization(job)`. `allowed_roots` limits where sources may come from; it does not decide whether an objective, command, or budget is appropriate. The orchestrator must review those. To expose only a curated job catalog, build your own MCP tool registrations and lifespan around `JobService`, including shutdown cancellation, instead of exposing the generic submit tool.

## Existing GPT, Grok, or Claude API loops

`step_engineer.bridge.ToolBridge` exposes the same local service in three formats:

| `bridge.tools(...)` | Parent API format |
| --- | --- |
| `"openai"` | OpenAI Responses flat function tools; `strict=False` |
| `"grok"` | Chat Completions `type: function` wrapper |
| `"claude"` | Claude tool definitions with `input_schema` |

```python
from pathlib import Path

from step_engineer.bridge import ToolBridge
from step_engineer.service import JobService

service = JobService(
    Path("/absolute/path/to/optimization-runs"),
    [Path("/absolute/path/to/your-project")],
)
bridge = ToolBridge(service)

# Select the format expected by your existing parent API client.
tools = bridge.tools("openai")  # or "grok" or "claude"

# Inside the host application's existing async tool loop:
# result = await bridge.dispatch(tool_name, decoded_arguments)
# Send result back with the matching parent-provider tool-call ID.
# On application shutdown: await service.close()
```

The host must provide the Step key before submitting a live job. It may explicitly load a private dotenv file during application startup; never accept a key from model-generated tool arguments.

The bridge validates `JobSpec` and dispatches locally. It does not call OpenAI, xAI, or Anthropic, create their clients, attach their tool-result envelopes, or manage the parent's conversation. Those remain the host application's responsibilities. Tool schemas and all four dispatch paths have offline tests; this is not a claim of paid compatibility testing with all three parent providers.

A cloud model cannot reach your Mac just because a prompt names `localhost`. Use a trusted local executor with access to the allowed source directories. This project does not provide a public remote MCP endpoint. You only need the credentials for the parent provider you actually use, plus Step credentials for live optimization.

Relevant tool-calling protocols: [OpenAI](https://developers.openai.com/api/docs/guides/function-calling), [xAI](https://docs.x.ai/developers/tools/function-calling), and [Anthropic](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview). Client setup details may vary by version; check the linked official documentation for your installation.
