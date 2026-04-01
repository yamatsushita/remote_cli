# Remote CLI

A serverless bridge between a **GitHub Pages web interface** and a **local CLI client**, using **GitHub Issues** as the communication channel.

```
┌──────────────┐    GitHub Issues     ┌──────────────┐
│  Web UI      │◄────────────────────►│  Python CLI  │
│ (GitHub Pages│   (comments as       │  (your PC)   │
│   + JS)      │    messages)         │              │
└──────────────┘                      └──────────────┘
```

## How it works

1. The **Python client** runs on your desktop and creates a GitHub Issue labeled `remote-cli`.
2. The **web interface** (hosted on GitHub Pages) displays the issue's comments as a chat.
3. You type prompts in the web form → they become issue comments.
4. The Python client polls for new comments, processes them, and posts responses.
5. No server required – GitHub is the only infrastructure.

## Quick start

### 0. Fork or clone this repo

Fork this repository to your own GitHub account, or use it as a template. Enable **GitHub Pages** from `Settings → Pages → Source: main, /docs`.

### 1. Generate a GitHub Personal Access Token

Create a [fine-grained PAT](https://github.com/settings/tokens?type=beta) with **Issues read/write** permission on your repository.

### 2. Start the Python client(s)

```bash
pip install -r requirements.txt

# Run from inside your cloned repo (auto-detects owner/repo)
python client.py --token ghp_xxx --name desktop

# Or specify owner/repo explicitly
python client.py --token ghp_xxx --owner YOUR_USER --repo remote_cli --name laptop

# Create a fresh session
python client.py --new --name server1

# Join a specific session
python client.py --join 1 --name worker-2
```

### 3. Open the web interface

Go to **https://YOUR_USER.github.io/remote_cli/** (the repo auto-detects from the URL) and enter:

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

| Command         | Description                        |
|-----------------|------------------------------------|
| `ping`          | Check if the client is alive       |
| `status`        | Show host system information       |
| `shell <cmd>`   | Run a shell command (30 s timeout) |
| `help`          | List available commands            |

## Architecture

| Component       | Technology         | Role                          |
|-----------------|--------------------|-------------------------------|
| Web UI          | GitHub Pages + JS  | Chat interface, prompt input  |
| Message bus     | GitHub Issues API  | Transport layer               |
| Local client(s) | Python + requests  | Command execution, responses  |

- **Prompts** are comments: `### 🧑 Prompt` (all) or `### 🧑 Prompt ➜ client-name` (targeted)
- **Responses** are comments: `### 🤖 Response [client-name]`
- **Status** updates are comments: `### 📡 Status [client-name]`
