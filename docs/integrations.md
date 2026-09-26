# Connect a parent agent

[English README](../README.md) · [繁體中文](README.zh-TW.md) · [Delegation instructions](parent-agent-instructions.md)

Step Engineer keeps your existing parent model, authentication, conversation loop, and reasoning settings unchanged. A job's `reasoning_effort` controls only the Step worker and defaults to `medium`. Ultra, when available, remains a setting of the parent application.

```text
Parent agent
  -> Local MCP host or API tool executor
  -> Step Engineer -> Step API + isolated local checks
  -> Measured results and patch
  -> Parent review and application
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
