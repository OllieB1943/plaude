# Plaude Code

Voice-to-Claude automation. Record on Plaud, say "send to claude", and Claude Code executes your instructions automatically.

## How it works

1. Record a voice memo on your Plaud device
2. Say a trigger phrase like *"send to claude"* or *"claude fix this"*
3. Plaud syncs the transcript to Google Drive
4. Plaude Code detects the trigger, figures out which project you were talking about, writes a `CLAUDE.md` with your instructions, and launches Claude Code in that directory

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://github.com/anthropics/claude-code) — `npm install -g @anthropic-ai/claude-code`
- [cloudflared](https://developers.cloudflare.com/cloudflared/) — `brew install cloudflare/cloudflare/cloudflared`
- A Google account
- A Plaud device with Google Drive sync enabled

## Setup

```bash
# Clone
git clone https://github.com/OllieB1943/plaude-code.git
cd plaude-code

# Install dependencies
pip install -r requirements.txt

# Run the setup wizard (handles Google OAuth + config)
python3 setup.py

# Start
./start.sh
```

## Trigger phrases

Say any of these in your recording:

| Phrase | Example |
|--------|---------|
| send to claude | "...send to claude" |
| send this to claude | "send this to claude when done" |
| claude fix | "claude fix the auth bug" |
| claude finish | "claude finish the dashboard" |
| claude should | "claude should refactor this" |
| claude execute | "claude execute the migration" |
| claude do this | "claude do this please" |
| claude handle | "claude handle the rest" |
| claude code this | "claude code this up" |
| go to claude | "this should go to claude" |
| for claude | "this is for claude" |
| claude [any verb] | catch-all for anything starting with "claude" |

## Project matching

Plaude Code scans the transcript for folder names that exist in your `projects_root`. If your project is called `my-app`, just mention "my-app" in your recording and it'll match automatically.

If nothing matches, a fallback `CLAUDE.md` is written to `~/Desktop/plaude-unmatched/` — move it to the right project and run `claude` manually.

## Launchers

Plaude Code supports two ways to hand off to Claude. Set `launcher` in `config.json`:

| Value | What happens |
|-------|-------------|
| `"cli"` | Writes `CLAUDE.md` to the project directory and launches Claude Code CLI (default) |
| `"cowork"` | Drops a task file into `cowork_inbox` for Claude Cowork to pick up automatically |
| `"both"` | Does both simultaneously |

**Using Cowork:**
1. Set `"launcher": "cowork"` (or `"both"`) in `config.json`
2. Set `"cowork_inbox"` to a folder Claude Cowork is watching (default: `~/claude-inbox`)
3. In the Claude desktop app, point a Cowork session at that inbox folder and tell it: *"When a new .md file appears here, read it and execute the instructions inside it"*
4. Leave Cowork running — it will automatically pick up and act on every transcript Plaude Code drops in

## Config

Edit `config.json` to customise behaviour:

```json
{
  "drive_folder_id": "your-folder-id",
  "projects_root": "~/projects",
  "trigger_phrases": ["send to claude", "..."],
  "claude_cmd": "claude",
  "auto_launch": true,
  "poll_interval_seconds": 10,
  "launcher": "cli",
  "cowork_inbox": "~/claude-inbox"
}
```

## License

MIT
