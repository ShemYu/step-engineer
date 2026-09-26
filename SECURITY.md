# Security and data handling

Step Engineer is a local, single-user engineering tool. It is not a service for
running arbitrary code submitted by strangers and is not a VM-grade security
boundary.

## What leaves the machine

A live job sends its objective, selected visible source files and development
check feedback to the configured StepFun API. The API key authenticates requests
to `https://api.stepfun.ai/v1`; redirects, environment proxies and automatic
retries are disabled. Choose files deliberately: source files and test output
can contain sensitive information even when their filenames look harmless.

`final_only_files` are withheld from the model's development tools. They become
readable by the candidate process during final validation. This protects against
simple test overfitting; it is not a cryptographic or adversarial secrecy boundary.

## Local execution

On macOS, fixed parent-owned commands run under `sandbox-exec` with networking
denied, a read-only workspace, an environment without inherited credentials, and
per-command writable scratch space. Output, time and scratch storage are bounded.
Other platforms refuse candidate execution instead of falling back to an
unsandboxed process.

Aggregate scratch bytes and entry counts are monitored while a command runs and
checked again after process cleanup. A completed command can therefore have exit
code zero and still be rejected for storage use. This monitoring is not an
instantaneous filesystem quota; transient writes between checks can exceed it.

The sandbox permits runtime library reads. Keep credentials out of interpreter
and dependency directories. Same-interpreter test tampering, deliberately escaped
process groups, resource-limit races and malicious installed dependencies require
stronger isolation. Inspect accepted patches and use independent checks before
applying changes to a project. An API request that times out or is cancelled may
still incur provider charges.

## Keeping credentials private

Store keys in an environment variable or an explicitly selected local dotenv
file. For example, copy `.env.example` to `.env.local`, restrict it with
`chmod 600 .env.local`, then edit it locally. Do not put a real key in a command
line, job JSON, issue, tool argument or committed MCP configuration. A dotenv file
does not get loaded implicitly; pass `--env-file` when needed.

The repository excludes dotenv files other than the empty `.env.example`, run
directories, local experiments, account checks and generated media. The public
tree checker inspects tracked/staged files, and packaging uses explicit file
allowlists. These checks reduce accidental disclosure; they do not replace
review. If a key is exposed, revoke it with its provider.

## Reporting a vulnerability

Use GitHub's **Security → Report a vulnerability** on this repository when private
reporting is available. Do not post live credentials, private source, local
artwork or an exploit against another person's system in a public issue. If
private reporting is unavailable, open a minimal issue requesting a private
contact channel without including sensitive details.

There is no guaranteed response time. Include the affected version, operating
system and a minimal reproduction using synthetic data.
