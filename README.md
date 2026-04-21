# Remote CLI

A serverless bridge that lets you interact with a **local [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli)** remotely through **GitHub Issues**.

```
┌──────────────┐    GitHub Issues     ┌──────────────┐
│  You         │◄────────────────────►│  remote_cli   │
│ (browser on  │   (*_sessions repo   │  (your PC)   │
│  any device) │    comments as       │  ↕ gh copilot│
│              │    messages)         │              │
└──────────────┘                      └──────────────┘
```

## How it works

1. **`remote_cli.py`** runs on your desktop and creates a GitHub Issue labeled `remote-cli` in a companion sessions repository.
2. You open the issue in any browser and **post a comment** with your prompt.
3. `remote_cli.py` polls for new comments, forwards prompts to the **GitHub Copilot CLI** (`gh copilot`), and posts responses back as issue comments.
4. No server required – GitHub is the only infrastructure.

## Prerequisites

- **Python 3.10+** with `requests` (`pip install -r requirements.txt`)
- **[GitHub CLI](https://cli.github.com/)** (`gh`) with the **Copilot extension** installed and authenticated
- A **GitHub Personal Access Token** with Issues read/write access

## Quick start

### 0. Set up

1. **Clone** this repository
2. **Create** a **private** companion `*_sessions` repository (e.g. `remote_cli_sessions`) for session issues

> **Why two repos?** The sessions repo keeps Copilot CLI session issues separate from code issues (bugs, feature requests).
>
> **Why private?** Session issues may contain sensitive information (commands, output, file contents). Keep the sessions repo private to restrict access.

### 1. Generate a GitHub Personal Access Token

Create a [fine-grained PAT](https://github.com/settings/tokens?type=beta) with **Issues read/write** permission on your **sessions** repository.

### 2. Start the client

```bash
pip install -r requirements.txt

# Start a client (--name is required; auto-detects repo)
python remote_cli.py --token ghp_xxx --name desktop

# Specify the sessions repo explicitly
python remote_cli.py --token ghp_xxx --owner YOUR_USER --repo remote_cli_sessions --name laptop

# Specify a Copilot model
python remote_cli.py --token ghp_xxx --name desktop --model claude-sonnet-4

# Force a new session even if this client already has an open one
python remote_cli.py --token ghp_xxx --new --name desktop

# Join the latest open session from any client
python remote_cli.py --token ghp_xxx --latest --name worker-2
```

### Command-line arguments

| Argument              | Required | Description                                                       |
|-----------------------|----------|-------------------------------------------------------------------|
| `--name <NAME>`       | **Yes**  | Client name. Used for routing and as the working subfolder name.  |
| `--token <TOKEN>`     | Yes*     | GitHub PAT. Can also be set via `GITHUB_TOKEN` env var.           |
| `--owner <OWNER>`     | No       | Repository owner (auto-detected from git remote).                 |
| `--repo <REPO>`       | No       | Sessions repository name (auto-detected + `_sessions` suffix).    |
| `--model <MODEL>`     | No       | Model for `gh copilot` (e.g. `claude-sonnet-4`, `gpt-4o`).       |
| `--new`               | No       | Force-create a new session.                                       |
| `--join <N>`          | No       | Join an existing session by issue number.                         |
| `--latest`            | No       | Join the latest open session from any client.                     |

`--name` is **required** — it determines the client identity, session isolation, and the
working directory. On launch, `remote_cli.py` creates a subfolder `./<NAME>/` in the current
directory and uses it as the working directory for all Copilot CLI and shell commands.

Each `--name` gets its own isolated session. If a client with the same name
is already connected, the new one is rejected — use a different `--name`.

### 3. Send prompts via GitHub Issues

1. Open your **sessions repo** on GitHub (e.g. `https://github.com/YOUR_USER/remote_cli_sessions`)
2. Go to the **Issues** tab — you'll see an open issue created by the client (e.g. `desktop – HOSTNAME – 2026-04-02 08:44`)
3. **Post a comment** on the issue with your prompt — the client will pick it up, forward it to the Copilot CLI, and post the response

#### Examples

| You type as a comment          | What happens                                           |
|--------------------------------|--------------------------------------------------------|
| `\ping`                        | Client replies with a pong to confirm it's alive       |
| `\status`                      | Client replies with host system information            |
| `\shell ls -la`                | Client runs the shell command and posts the output     |
| `\clear`                       | Deletes all comments and resets Copilot CLI context    |
| `\esc`                         | Cancels the currently running Copilot CLI/shell task   |
| `\help`                        | Client lists all available commands                    |
| `list all files in src/`       | Forwarded to the Copilot CLI (`gh copilot`) for processing |

#### Targeting a specific client

If multiple clients are connected to the same session, prefix your comment with `➜ client-name` on the first line:

```
➜ desktop
\status
```

Without a prefix, prompts are sent to **all** clients.

## Multi-client support

Each client automatically gets its **own isolated session** (GitHub Issue). When you launch a
second client with a different `--name`, it creates a separate issue instead of overtaking the
first client's session. When a client disconnects, its issue is closed automatically.

- **Automatic isolation:** default behaviour finds an existing session *for this client name*,
  or creates a new one. Two clients with different names never share an issue by default.
- **Duplicate name protection:** launching a client whose name is already connected is rejected.
- **Explicit sharing:** use `--latest` to intentionally join another client's session.

## Built-in commands

Built-in commands start with `\` to distinguish them from regular prompts.

| Command          | Description                                |
|------------------|--------------------------------------------|
| `\ping`          | Check if the client is alive               |
| `\status`        | Show host system information               |
| `\shell <cmd>`   | Run a shell command (30 s timeout)        |
| `\clear`         | Delete all comments and reset Copilot CLI context |
| `\esc`           | Cancel the current Copilot CLI/shell task  |
| `\help`          | List available commands                    |

Any other text is forwarded to the **GitHub Copilot CLI** (`gh copilot`) as a prompt.

## Architecture

| Component       | Technology         | Role                                  |
|-----------------|--------------------|---------------------------------------|
| Message bus     | GitHub Issues API  | Transport layer (sessions repo)       |
| Local client    | Python (`remote_cli.py`) + `requests` | Polling, command dispatch   |
| AI backend      | GitHub Copilot CLI (`gh copilot`)     | Prompt processing           |

- **Prompts** are plain-text comments on the issue
- **Targeted prompts** have a first line: `➜ client-name`
- **Responses** are comments: `### 🤖 Response [client-name]`
- **Status** updates are comments: `### 📡 Status [client-name]`
- **Working directory** for each client is `./<NAME>/` relative to where `remote_cli.py` is launched
