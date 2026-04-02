#!/usr/bin/env python3
"""
Remote CLI Client

Polls a GitHub Issue for prompts posted via the web interface,
processes them locally, and posts responses back as comments.

Usage:
    python client.py --token ghp_xxx
    python client.py --new          # force a new session
    python client.py --join 3       # join issue #3
    python client.py --latest       # join latest open session

Environment:
    GITHUB_TOKEN   Personal Access Token (alternative to --token)
"""

import os
import re
import sys
import time
import uuid
import signal
import platform
import argparse
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests


class RemoteCLIClient:
    """Bridges GitHub Issues with local command execution."""

    LABEL = "remote-cli"
    POLL_INTERVAL = 5
    HEARTBEAT_INTERVAL = 60

    def __init__(self, token: str, owner: str, repo: str, name: str = "default"):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.name = name
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })
        self.issue_number: int | None = None
        self.processed_ids: set[int] = set()
        self.running = True
        self.last_heartbeat = 0.0
        self.status_comment_id: int | None = None
        # Copilot CLI session — one persistent session per client
        self.copilot_session_id = str(uuid.uuid4())
        self.copilot_config_dir = Path.home() / ".copilot-remote" / name
        self.copilot_config_dir.mkdir(parents=True, exist_ok=True)
        # Default working directory: sibling *_sessions repo folder / <name>
        self.working_dir = self._find_sessions_dir(repo, name)
        self._active_proc: subprocess.Popen | None = None

    # ── GitHub API ──────────────────────────────────────────────

    @staticmethod
    def _find_sessions_dir(repo: str, name: str) -> Path | None:
        """Locate the sibling *_sessions repo directory and create a
        per-client subdirectory (<name>) to use as cwd."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=5,
            )
            git_root = Path(result.stdout.strip())
            sessions_dir = git_root.parent / repo
            if sessions_dir.is_dir():
                client_dir = sessions_dir / name
                client_dir.mkdir(parents=True, exist_ok=True)
                return client_dir
        except Exception:
            pass
        return None

    def _api(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        last_resp = None
        for attempt in range(3):
            resp = self.session.request(method, url, **kwargs)
            if resp.status_code == 422 and attempt < 2:
                # GitHub secondary rate-limit / anti-abuse — retry after pause
                time.sleep(2 ** attempt)
                last_resp = resp
                continue
            resp.raise_for_status()
            return resp.json() if resp.content else None
        last_resp.raise_for_status()

    # ── Label ───────────────────────────────────────────────────

    def _ensure_label(self):
        try:
            self._api("GET", f"/labels/{self.LABEL}")
        except requests.HTTPError:
            self._api("POST", "/labels", json={
                "name": self.LABEL,
                "color": "0366d6",
                "description": "Remote CLI session",
            })

    # ── Session management ──────────────────────────────────────

    def create_session(self) -> int:
        self._ensure_label()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        hostname = platform.node()
        issue = self._api("POST", "/issues", json={
            "title": f"{self.name} – {hostname} – {ts}",
            "body": (
                "🖥️ **Remote CLI Session**\n\n"
                "This issue is the communication channel between the web "
                "interface and local CLI clients.\n\n"
                f"- **Started:** {ts}\n"
                f"- **Host:** {hostname}\n"
                f"- **First client:** `{self.name}`\n"
            ),
            "labels": [self.LABEL],
        })
        self.issue_number = issue["number"]
        print(f"✅ [{self.name}] Created session: Issue #{self.issue_number}")
        self._post_status("🟢 Connected and ready.")
        return self.issue_number

    def join_session(self, issue_number: int):
        self.issue_number = issue_number
        comments = self._api(
            "GET", f"/issues/{issue_number}/comments?per_page=100"
        )
        # Mark comments up to the last response/status as processed.
        # Comments posted AFTER that are pending prompts and will be
        # picked up on the first poll cycle.
        last_handled = -1
        for i, c in enumerate(comments):
            body = c.get("body", "")
            if body.startswith("### 🤖 Response") or body.startswith("### 📡 Status"):
                last_handled = i
        for i, c in enumerate(comments):
            if i <= last_handled:
                self.processed_ids.add(c["id"])
        pending = len(comments) - last_handled - 1
        print(
            f"✅ [{self.name}] Joined session: Issue #{issue_number} "
            f"({len(comments)} comments, {pending} pending)"
        )
        self._post_status("🟢 Connected and ready.")

    def find_own_session(self) -> int | None:
        """Find the latest open session created by this client (by name)."""
        issues = self._api(
            "GET",
            f"/issues?labels={self.LABEL}&state=open"
            "&sort=created&direction=desc&per_page=100",
        )
        for issue in issues:
            title = issue.get("title", "")
            if title.startswith(f"{self.name} –"):
                return issue["number"]
        return None

    def is_name_active(self) -> bool:
        """Check if another client with the same name is already connected."""
        issues = self._api(
            "GET",
            f"/issues?labels={self.LABEL}&state=open"
            "&sort=created&direction=desc&per_page=100",
        )
        for issue in issues:
            comments = self._api(
                "GET",
                f"/issues/{issue['number']}/comments?per_page=100",
            )
            # Walk backwards to find this client's latest status comment
            for c in reversed(comments):
                body = c.get("body", "")
                if body.startswith(f"### 📡 Status [{self.name}]"):
                    return "🟢" in body
        return False

    def find_latest_session(self) -> int | None:
        """Find the latest open session regardless of client name."""
        issues = self._api(
            "GET",
            f"/issues?labels={self.LABEL}&state=open"
            "&sort=created&direction=desc&per_page=1",
        )
        return issues[0]["number"] if issues else None

    # ── Comments ────────────────────────────────────────────────

    def _post_comment(self, body: str):
        return self._api(
            "POST",
            f"/issues/{self.issue_number}/comments",
            json={"body": body},
        )

    def _post_status(self, text: str):
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        body = f"### 📡 Status [{self.name}]\n\n{text}\n\n_Updated: {now_utc}_"
        if self.status_comment_id:
            try:
                self._api(
                    "PATCH",
                    f"/issues/comments/{self.status_comment_id}",
                    json={"body": body},
                )
                return
            except requests.HTTPError:
                pass
        comment = self._post_comment(body)
        self.status_comment_id = comment["id"]
        self.processed_ids.add(comment["id"])

    def _post_response(self, text: str):
        comment = self._post_comment(f"### 🤖 Response [{self.name}]\n\n{text}")
        self.processed_ids.add(comment["id"])

    def _create_response_comment(self, text: str) -> int:
        """Create a response comment and return its ID."""
        comment = self._post_comment(
            f"### 🤖 Response [{self.name}]\n\n{text}"
        )
        self.processed_ids.add(comment["id"])
        return comment["id"]

    def _update_response_comment(self, comment_id: int, text: str):
        """Update an existing response comment in-place."""
        body = f"### 🤖 Response [{self.name}]\n\n{text}"
        self._api(
            "PATCH",
            f"/issues/comments/{comment_id}",
            json={"body": body},
        )

    def _clear_comments(self):
        """Delete all comments on the current issue."""
        comments = self._api(
            "GET", f"/issues/{self.issue_number}/comments?per_page=100"
        )
        count = 0
        for c in comments:
            try:
                self._api("DELETE", f"/issues/comments/{c['id']}")
                count += 1
            except Exception:
                pass
        self.processed_ids.clear()
        self.status_comment_id = None
        self.copilot_session_id = str(uuid.uuid4())
        print(f"   🧹 Cleared {count} comments")
        self._post_status("🟢 Client connected and ready.")
        self._post_response(
            f"🧹 Cleared {count} comments. "
            "Copilot conversation context has been reset."
        )

    # ── Polling ─────────────────────────────────────────────────

    def _get_new_prompts(self) -> list[dict]:
        comments = self._api(
            "GET", f"/issues/{self.issue_number}/comments?per_page=100"
        )
        prompts = []
        for c in comments:
            if c["id"] in self.processed_ids:
                continue
            body = c.get("body", "")
            # Skip our own responses and status updates
            if body.startswith("### 🤖 Response") or body.startswith("### 📡 Status"):
                self.processed_ids.add(c["id"])
                continue
            # Parse target from "➜ target\n" prefix (first line)
            target = "all"
            text = body
            target_match = re.match(r"^➜\s*(\S+)\s*\n", body)
            if target_match:
                target = target_match.group(1)
                text = body[target_match.end():]
            # Only process if targeted at us or broadcast
            if target.lower() not in (self.name.lower(), "all"):
                continue  # leave unprocessed for the target client
            prompts.append({
                "id": c["id"],
                "text": text.strip(),
                "target": target,
                "user": c["user"]["login"],
                "ts": c["created_at"],
            })
            self.processed_ids.add(c["id"])
        return prompts

    def _check_for_esc(self) -> bool:
        """Check if a \\esc comment has been posted since we last looked."""
        try:
            comments = self._api(
                "GET", f"/issues/{self.issue_number}/comments?per_page=100"
            )
            for c in comments:
                if c["id"] in self.processed_ids:
                    continue
                body = c.get("body", "").strip()
                if body.startswith("### 🤖 Response") or body.startswith("### 📡 Status"):
                    self.processed_ids.add(c["id"])
                    continue
                # Strip target prefix
                target_match = re.match(r"^➜\s*(\S+)\s*\n", body)
                if target_match:
                    target = target_match.group(1)
                    text = body[target_match.end():].strip()
                    if target.lower() not in (self.name.lower(), "all"):
                        continue
                else:
                    text = body
                if text.lower() == "\\esc":
                    self.processed_ids.add(c["id"])
                    print(f"   ⛔ \\esc received — cancelling")
                    return True
        except Exception:
            pass
        return False

    # ── Prompt handling ─────────────────────────────────────────

    def process_prompt(self, prompt: dict) -> str:
        text = prompt["text"].strip()

        if text.lower() == "\\ping":
            return f"🏓 Pong from **{self.name}**!"

        if text.lower() == "\\clear":
            self._clear_comments()
            return None

        if text.lower() == "\\esc":
            if self._active_proc and self._active_proc.poll() is None:
                self._active_proc.kill()
                return "⛔ Cancelled current processing."
            return "ℹ️ Nothing is running."

        if text.lower() == "\\help":
            return (
                f"**Available commands** (client: `{self.name}`)\n\n"
                "| Command | Description |\n"
                "|---------|-------------|\n"
                "| `\\ping` | Check if client is alive |\n"
                "| `\\status` | System information |\n"
                "| `\\shell <cmd>` | Run a shell command (30 s timeout) |\n"
                "| `\\clear` | Delete all comments and reset context |\n"
                "| `\\esc` | Cancel the current processing |\n"
                "| `\\help` | This help message |\n"
                "| _anything else_ | Sent to GitHub Copilot CLI |\n"
            )

        if text.lower() == "\\status":
            return (
                f"**System information** (client: `{self.name}`)\n\n"
                f"- **Client name:** {self.name}\n"
                f"- **Host:** {platform.node()}\n"
                f"- **OS:** {platform.system()} {platform.release()}\n"
                f"- **Python:** {platform.python_version()}\n"
                f"- **Copilot session:** `{self.copilot_session_id}`\n"
                f"- **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )

        if text.lower().startswith("\\shell "):
            return self._run_shell(text[7:].strip())

        return self._run_copilot(text)

    def _run_copilot(self, prompt: str) -> str | None:
        """Send a prompt to Copilot CLI with streaming progress updates.

        Creates a response comment immediately ("thinking…"), updates it
        with intermediate output every few seconds, and finalises it when
        Copilot completes.  Returns ``None`` to signal the caller that
        the response has already been posted.
        """
        STREAM_UPDATE_INTERVAL = 5   # seconds between progress edits
        IDLE_TIMEOUT = 86400         # 24-hour idle limit (no new output)

        # ── Post the initial "thinking" comment ──────────────────
        comment_id = self._create_response_comment(
            "⏳ _Copilot is thinking…_"
        )
        start_time = time.time()

        try:
            cmd = [
                "gh", "copilot",
                "-p", prompt,
                "--allow-all",
                f"--resume={self.copilot_session_id}",
                f"--config-dir={self.copilot_config_dir}",
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                cwd=self.working_dir,
                env={**os.environ, "NO_COLOR": "1", "PYTHONUTF8": "1"},
            )
            self._active_proc = proc

            # Reader threads — accumulate lines in shared lists
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            lock = threading.Lock()

            def _read_stream(stream, lines):
                try:
                    while True:
                        line = stream.readline()
                        if not line:
                            break
                        with lock:
                            lines.append(line)
                except Exception:
                    pass

            t_out = threading.Thread(
                target=_read_stream, args=(proc.stdout, stdout_lines),
                daemon=True,
            )
            t_err = threading.Thread(
                target=_read_stream, args=(proc.stderr, stderr_lines),
                daemon=True,
            )
            t_out.start()
            t_err.start()

            # ── Poll for intermediate output ─────────────────────
            last_update_time = start_time
            last_snapshot = ""
            last_output_len = 0        # track output growth for idle detection
            last_activity_time = start_time

            while proc.poll() is None:
                time.sleep(0.5)
                elapsed = time.time() - start_time

                # Check for \esc cancel request
                if self._check_for_esc():
                    proc.kill()
                    proc.wait()
                    self._active_proc = None
                    self._update_response_comment(
                        comment_id,
                        "⛔ _Cancelled by user._",
                    )
                    return None

                # Check for new output to reset idle timer
                with lock:
                    current_len = len(stdout_lines) + len(stderr_lines)
                if current_len != last_output_len:
                    last_output_len = current_len
                    last_activity_time = time.time()

                # Idle timeout — no new output for IDLE_TIMEOUT seconds
                if time.time() - last_activity_time > IDLE_TIMEOUT:
                    proc.kill()
                    proc.wait()
                    self._update_response_comment(
                        comment_id,
                        "⏰ Copilot timed out (no output for 24 hours).",
                    )
                    return None

                # Periodic progress update
                now = time.time()
                if now - last_update_time >= STREAM_UPDATE_INTERVAL:
                    with lock:
                        cur_out = "".join(stdout_lines)
                        cur_err = "".join(stderr_lines)

                    raw = cur_out or cur_err
                    display = re.sub(
                        r"\x1b\[[0-9;]*[a-zA-Z]", "", raw
                    ).strip()
                    elapsed_str = f"{int(elapsed)}s"

                    if display and display != last_snapshot:
                        # Show partial output + spinner
                        preview = display[:60000]
                        body = (
                            f"{preview}\n\n"
                            f"⏳ _Copilot is still working… "
                            f"({elapsed_str} elapsed)_"
                        )
                        last_snapshot = display
                    else:
                        body = (
                            f"⏳ _Copilot is working… "
                            f"({elapsed_str} elapsed)_"
                        )

                    try:
                        self._update_response_comment(comment_id, body)
                    except Exception:
                        pass
                    last_update_time = now

            # ── Process exited — collect final output ────────────
            self._active_proc = None
            t_out.join(timeout=5)
            t_err.join(timeout=5)

            with lock:
                stdout = "".join(stdout_lines)
                stderr = "".join(stderr_lines)

            # Clean ANSI escape codes
            stdout = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", stdout)
            stderr = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", stderr)

            # Strip usage summary block
            usage_re = r"\n*Total usage est:.*"
            stdout_clean = re.sub(
                usage_re, "", stdout, flags=re.DOTALL
            ).strip()
            stderr_clean = re.sub(
                usage_re, "", stderr, flags=re.DOTALL
            ).strip()

            output = stdout_clean or stderr_clean
            if not output:
                output = (
                    f"_Copilot returned no output "
                    f"(exit code {proc.returncode})._"
                )
            if len(output) > 60000:
                output = output[:60000] + "\n\n_(truncated)_"

            # Final update — replace progress indicator with "Done"
            elapsed_total = int(time.time() - start_time)
            self._update_response_comment(
                comment_id,
                f"{output}\n\n✅ _Done ({elapsed_total}s)_",
            )
            return None

        except FileNotFoundError:
            self._update_response_comment(
                comment_id,
                "❌ `gh copilot` not found. "
                "Install GitHub CLI with Copilot extension.",
            )
            return None
        except Exception as e:
            self._update_response_comment(
                comment_id,
                f"❌ Copilot error: {type(e).__name__}: {e}",
            )
            return None

    def _run_shell(self, cmd: str) -> str:
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                encoding="utf-8", errors="replace", timeout=30,
                cwd=self.working_dir,
            )
            parts = []
            if result.stdout:
                parts.append(f"**stdout:**\n```\n{result.stdout[:3000]}\n```")
            if result.stderr:
                parts.append(f"**stderr:**\n```\n{result.stderr[:1500]}\n```")
            parts.append(f"_Exit code: {result.returncode}_")
            return "\n\n".join(parts) if parts else "_No output_"
        except subprocess.TimeoutExpired:
            return "⏰ Command timed out (30 s limit)."
        except Exception as e:
            return f"❌ Error: {e}"

    # ── Heartbeat ───────────────────────────────────────────────

    def _heartbeat(self):
        now = time.time()
        if now - self.last_heartbeat >= self.HEARTBEAT_INTERVAL:
            self._post_status("🟢 Client connected and ready.")
            self.last_heartbeat = now

    # ── Main loop ───────────────────────────────────────────────

    def run(self):
        print(f"🔄 [{self.name}] Polling Issue #{self.issue_number} every {self.POLL_INTERVAL}s")
        print(f"   Responds to prompts targeted at: \"{self.name}\" or \"all\"")
        print(f"   Working dir:     {self.working_dir or os.getcwd()}")
        print(f"   Copilot session: {self.copilot_session_id}")
        print(f"   Copilot config:  {self.copilot_config_dir}")
        print("   Press Ctrl+C to stop\n")

        while self.running:
            try:
                prompts = self._get_new_prompts()
                for p in prompts:
                    target_info = f" (➜ {p['target']})" if p.get('target') != 'all' else ''
                    print(f"📨 @{p['user']}{target_info}: {p['text'][:100]}")
                    self._post_status(
                        f"⏳ Processing prompt from @{p['user']}…"
                    )
                    response = self.process_prompt(p)
                    if response is not None:
                        self._post_response(response)
                    print(f"   ✅ Response posted")
                    self._post_status("🟢 Client connected and ready.")
                    self.last_heartbeat = time.time()

                if not prompts:
                    self._heartbeat()

                time.sleep(self.POLL_INTERVAL)

            except KeyboardInterrupt:
                break
            except requests.RequestException as e:
                print(f"⚠️  API error: {e}")
                time.sleep(self.POLL_INTERVAL * 2)
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(self.POLL_INTERVAL)

        print(f"\n🛑 [{self.name}] Shutting down…")
        try:
            self._post_status(f"🔴 Client `{self.name}` disconnected.")
            self._api("PATCH", f"/issues/{self.issue_number}", json={
                "state": "closed",
            })
            print(f"   Issue #{self.issue_number} closed.")
        except Exception:
            pass


# ── CLI entry point ─────────────────────────────────────────────

def _detect_repo_from_git() -> tuple[str, str] | None:
    """Try to extract owner from the git remote URL.

    Returns (owner, sessions_repo) where sessions_repo is the
    companion '*_sessions' repository used for issue-based communication.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = result.stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url)
        if m:
            owner = m.group(1)
            repo = m.group(2)
            # Use the companion _sessions repo for issues
            if not repo.endswith("_sessions"):
                repo = repo + "_sessions"
            return owner, repo
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Remote CLI Client – bridge GitHub ↔ local shell"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub PAT (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--owner",
        help="Repository owner (auto-detected from git remote if omitted)",
    )
    parser.add_argument(
        "--repo",
        help="Sessions repository name (default: auto-detect + '_sessions')",
    )
    parser.add_argument(
        "--name",
        default=platform.node(),
        help="Client name for multi-client routing (default: hostname)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--new", action="store_true", help="Create a new session")
    group.add_argument("--join", type=int, metavar="N", help="Join issue #N")
    group.add_argument(
        "--latest", action="store_true", help="Join the latest session"
    )
    args = parser.parse_args()

    if not args.token:
        print("❌ Token required. Use --token or set GITHUB_TOKEN.")
        sys.exit(1)

    owner = args.owner
    repo = args.repo
    if not owner or not repo:
        detected = _detect_repo_from_git()
        if detected:
            owner = owner or detected[0]
            repo = repo or detected[1]
        else:
            print(
                "❌ Could not detect repository. "
                "Use --owner and --repo, or run from inside a git clone."
            )
            sys.exit(1)

    client = RemoteCLIClient(args.token, owner, repo, args.name)
    signal.signal(signal.SIGINT, lambda *_: setattr(client, "running", False))

    # Reject launch if another client with the same name is already online
    if client.is_name_active():
        print(
            f"❌ A client named '{args.name}' is already connected. "
            "Use --name to choose a different name."
        )
        sys.exit(1)

    if args.join:
        client.join_session(args.join)
    elif args.new:
        client.create_session()
    elif args.latest:
        issue = client.find_latest_session()
        if issue:
            client.join_session(issue)
        else:
            print("No open session found – creating a new one…")
            client.create_session()
    else:
        # Default: find this client's own session, or create a new one
        issue = client.find_own_session()
        if issue:
            client.join_session(issue)
        else:
            print(f"No open session for '{args.name}' – creating a new one…")
            client.create_session()

    client.run()


if __name__ == "__main__":
    main()
