# Remote CLI

A serverless bridge that lets you interact with a **local CLI client** remotely through **GitHub Issues**.

```
┌──────────────┐    GitHub Issues     ┌──────────────┐
│  You         │◄────────────────────►│  Python CLI  │
│ (browser on  │   (*_sessions repo   │  (your PC)   │
│  any device) │    comments as       │              │
│              │    messages)         │              │
└──────────────┘                      └──────────────┘
```

## How it works

1. The **Python client** runs on your desktop and creates a GitHub Issue labeled `remote-cli`.
2. You open the issue in any browser and **post a comment** with your prompt.
3. The Python client polls for new comments, processes them, and posts responses back as comments.
4. No server required – GitHub is the only infrastructure.

## Quick start

### 0. Set up

1. **Clone** this repository (code + Python client)
2. **Create** a **private** companion `*_sessions` repository (e.g. `remote_cli_sessions`) for session issues

> **Why two repos?** The sessions repo keeps CLI session issues separate from code issues (bugs, feature requests).
>
> **Why private?** Session issues may contain sensitive information (commands, output, file contents). Keep the sessions repo private to restrict access.

### 1. Generate a GitHub Personal Access Token

Create a [fine-grained PAT](https://github.com/settings/tokens?type=beta) with **Issues read/write** permission on your **sessions** repository.

### 2. Start the Python client

```bash
pip install -r requirements.txt

# Start a client (auto-detects repo; resumes its own session or creates one)
python client.py --token ghp_xxx --name desktop

# Specify the sessions repo explicitly
python client.py --token ghp_xxx --owner YOUR_USER --repo remote_cli_sessions --name laptop

# Force a new session even if this client already has an open one
python client.py --token ghp_xxx --new --name desktop

# Join the latest open session from any client
python client.py --token ghp_xxx --latest --name worker-2
```

Each `--name` gets its own isolated session. If a client with the same name
is already connected, the new one is rejected — use a different `--name`.

### 3. Send prompts via GitHub Issues

1. Open your **sessions repo** on GitHub (e.g. `https://github.com/YOUR_USER/remote_cli_sessions`)
2. Go to the **Issues** tab — you'll see an open issue created by the client (e.g. `desktop – HOSTNAME – 2026-04-02 08:44`)
3. **Post a comment** on the issue with your prompt — the client will pick it up and respond

#### Examples

| You type as a comment          | What happens                                       |
|--------------------------------|----------------------------------------------------|
| `\ping`                        | Client replies with a pong to confirm it's alive   |
| `\status`                      | Client replies with host system information        |
| `\shell ls -la`                | Client runs the shell command and posts the output |
| `\clear`                       | Deletes all comments and resets Copilot context    |
| `\esc`                         | Cancels the currently running Copilot/shell task   |
| `\help`                        | Client lists all available commands                |
| `list all files in src/`       | Sent to GitHub Copilot CLI for processing          |

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

| Command          | Description                              |
|------------------|------------------------------------------|
| `\ping`          | Check if the client is alive             |
| `\status`        | Show host system information             |
| `\shell <cmd>`   | Run a shell command (30 s timeout)       |
| `\clear`         | Delete all comments and reset context    |
| `\esc`           | Cancel the current processing            |
| `\help`          | List available commands                  |

Any other text is treated as a prompt and sent to GitHub Copilot CLI.

## Architecture

| Component       | Technology         | Role                          |
|-----------------|--------------------|-------------------------------|
| Message bus     | GitHub Issues API  | Transport layer (sessions repo)|
| Local client(s) | Python + requests  | Command execution, responses  |

- **Prompts** are plain-text comments on the issue
- **Targeted prompts** have a first line: `➜ client-name`
- **Responses** are comments: `### 🤖 Response [client-name]`
- **Status** updates are comments: `### 📡 Status [client-name]`
