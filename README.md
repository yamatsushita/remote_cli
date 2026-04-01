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

### 1. Generate a GitHub Personal Access Token

Create a [fine-grained PAT](https://github.com/settings/tokens?type=beta) with **Issues read/write** permission on this repository.

### 2. Start the Python client

```bash
pip install -r requirements.txt

# Using environment variable
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
python client.py

# Or pass token directly
python client.py --token ghp_xxxxxxxxxxxx

# Create a fresh session
python client.py --new

# Join a specific session
python client.py --join 1
```

### 3. Open the web interface

Go to **https://yamatsushita.github.io/remote_cli/** and enter:

- Your GitHub PAT
- Repository: `yamatsushita/remote_cli`

Select the active session and start chatting.

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
| Local client    | Python + requests  | Command execution, responses  |

- **Prompts** are comments starting with `### 🧑 Prompt`
- **Responses** are comments starting with `### 🤖 Response`
- **Status** updates are comments starting with `### 📡 Status`
