# Remote CLI

A serverless bridge between a **GitHub Pages web interface** and a **local CLI client**, using **GitHub Issues** as the communication channel.

```
┌──────────────┐    GitHub Issues     ┌──────────────┐
│  Web UI      │◄────────────────────►│  Python CLI  │
│ (GitHub Pages│   (*_sessions repo   │  (your PC)   │
│  on sessions │    comments as       │              │
│   repo)      │    messages)         │              │
└──────────────┘                      └──────────────┘
```

## How it works

1. The **Python client** runs on your desktop and creates a GitHub Issue labeled `remote-cli`.
2. The **web interface** (hosted on GitHub Pages) displays the issue's comments as a chat.
3. You type prompts in the web form → they become issue comments.
4. The Python client polls for new comments, processes them, and posts responses.
5. No server required – GitHub is the only infrastructure.

## Quick start

### 0. Set up your repositories

1. **Fork** this repository (code + Python client)
2. **Create** a companion `*_sessions` repository (e.g. `remote_cli_sessions`) for the web UI and session issues
3. Copy `docs/index.html` from this repo (or from [yamatsushita/remote_cli_sessions](https://github.com/yamatsushita/remote_cli_sessions)) into `docs/` of your sessions repo
4. Enable **GitHub Pages** on the sessions repo: `Settings → Pages → Source: main, /docs`

> **Why two repos?** The sessions repo keeps CLI session issues separate from code issues (bugs, feature requests).

### 1. Generate a GitHub Personal Access Token

Create a [fine-grained PAT](https://github.com/settings/tokens?type=beta) with **Issues read/write** permission on your **sessions** repository.

### 2. Start the Python client(s)

```bash
pip install -r requirements.txt

# Run from inside your cloned repo (auto-detects owner, uses *_sessions repo)
python client.py --token ghp_xxx --name desktop

# Or specify the sessions repo explicitly
python client.py --token ghp_xxx --owner YOUR_USER --repo remote_cli_sessions --name laptop

# Create a fresh session
python client.py --new --name server1

# Join a specific session
python client.py --join 1 --name worker-2
```

### 3. Open the web interface

Go to **https://YOUR_USER.github.io/remote_cli_sessions/** (auto-detects from the URL) and enter:

- Your GitHub PAT
- Repository (pre-filled if opened from GitHub Pages)

Select the active session. Use the **"Send to"** dropdown to target a specific client or broadcast to all.

## Multi-client support

Multiple clients can join the same session. Each client has a unique `--name` (defaults to hostname).

- **Target a specific client:** select it from the "Send to" dropdown in the web UI
- **Broadcast to all:** select "All clients" (default)
- Each client only picks up prompts addressed to it or to `all`
- Status badges show which clients are online

## Built-in commands

Built-in commands start with `\` to distinguish them from regular prompts.

| Command          | Description                        |
|------------------|------------------------------------|
| `\ping`          | Check if the client is alive       |
| `\status`        | Show host system information       |
| `\shell <cmd>`   | Run a shell command (30 s timeout) |
| `\help`          | List available commands            |

Any other text is treated as a prompt and echoed back by default.

## Architecture

| Component       | Technology         | Role                          |
|-----------------|--------------------|-------------------------------|
| Web UI          | GitHub Pages + JS  | Chat interface (sessions repo)|
| Message bus     | GitHub Issues API  | Transport layer (sessions repo)|
| Local client(s) | Python + requests  | Command execution, responses  |

- **Prompts** are plain-text comments (any comment not from the client)
- **Targeted prompts** have a first line: `➜ client-name`
- **Responses** are comments: `### 🤖 Response [client-name]`
- **Status** updates are comments: `### 📡 Status [client-name]`
