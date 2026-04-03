# Reddit Campaign CLI

Automate a 30-day Reddit marketing campaign through your Chrome browser. No Reddit API keys needed.

A Chrome extension + [kimi AI](https://kimi.moonshot.cn/) handles karma building, seeding comments, and posting — all through your actual logged-in browser session.

## How it works

```
┌──────────────┐   WebSocket    ┌─────────────────┐    Chrome    ┌────────┐
│  Python CLI  │◄──(port 9877)──►│ Chrome Extension │◄── CDP/DOM ──►│ Reddit │
│  main.py     │                │ background.js   │             │        │
└──────┬───────┘                └────────┬────────┘             └────────┘
       │                                 │
  campaign.toml                  Your login session
  SQLite DB                      (no API keys)
```

1. Configure your product, target subreddits, and tone in `campaign.toml`
2. A 30-day schedule is auto-generated in 4 phases
3. kimi AI writes contextual comments/posts based on existing discussions
4. The Chrome extension automates browser actions via Chrome DevTools Protocol
5. Everything is tracked in a local SQLite database

## Requirements

- Python 3.11+
- Google Chrome
- Reddit account (logged in via Chrome)
- [kimi CLI](https://kimi.moonshot.cn/) — AI-powered comment and post generation

## Quick start

```bash
# Clone
git clone https://github.com/user/reddit-campaign-cli.git
cd reddit-campaign-cli

# Install Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install click rich websockets

# Install Chrome extension
#   1. Open chrome://extensions
#   2. Enable "Developer mode" (top right)
#   3. Click "Load unpacked" → select the extension/ folder

# Log into Reddit in Chrome

# Create your campaign config
cp campaign.example.toml campaign.toml
# Edit campaign.toml with your product info
```

## Usage

### 1. Set up your campaign

```bash
# Interactive setup (creates campaign.toml)
python main.py campaign init

# Or copy and edit the example
cp campaign.example.toml campaign.toml
```

Edit `campaign.toml` with your product info:

```toml
[product]
name = "My App"
url = "https://github.com/user/my-app"
tagline = "A short description of your app"
category = "developer_tool"    # developer_tool, saas, app, service, community

[reddit]
username = "my_reddit_account"

[targets]
# Subreddits for karma building (NO product mentions)
karma_subs = [
    {sub = "programming", keywords = ["developer tools", "productivity"]},
    {sub = "webdev", keywords = ["frontend", "dev experience"]},
]

# Subreddits for seeding (naturally mention your product)
seed_subs = [
    {sub = "SideProject", keywords = ["side project", "indie dev"]},
]

# Subreddits for direct posts (ordered small → large)
post_subs = [
    {sub = "SideProject", title_hint = "Sharing my project"},
    {sub = "programming", title_hint = "Developer tool introduction"},
]

[content]
karma_tone = "helpful_expert"   # helpful_expert, friendly_user, curious_learner
seed_tone = "casual_mention"    # casual_mention, experience_share, comparison

[limits]
karma_comments_per_day = 4
seed_comments_per_day = 2
posts_per_day = 1
min_delay_seconds = 90
max_delay_seconds = 180
```

### 2. Preview before running

```bash
# See the full 30-day schedule
python main.py browser --schedule

# Dry run — shows what would happen without posting anything
python main.py browser --dry-run

# Preview generated comments for a specific day
python main.py campaign preview 5
```

### 3. Run the campaign

```bash
# Run the next incomplete day
python main.py browser

# Start from a specific day
python main.py browser --day 5

# Run all remaining days in sequence
python main.py browser --all

# Adjust delay between days (default 30s)
python main.py browser --all --delay 60
```

When you run `python main.py browser`, it:
1. Starts a WebSocket server on port 9877
2. Waits for the Chrome extension to connect
3. Verifies you're logged into Reddit
4. Executes the day's tasks (karma comments, seeding, posts)
5. Saves results to `data/campaign.db`

### 4. Monitor progress

```bash
# Campaign progress overview
python main.py browser --status

# Detailed activity history
python main.py campaign history

# Daily strategy report
python main.py report

# Terminal dashboard
python main.py dashboard

# Web dashboard (opens localhost:8090)
python main.py web
```

### 5. Manage the schedule

```bash
# View full 30-day plan with task details
python main.py campaign plan

# View a specific day's plan
python main.py campaign day 10

# Customize a day's tasks
python main.py campaign edit-day 5 \
  --clear-tasks \
  --add-karma commandline:terminal,cli \
  --add-seed webdev:developer tools

# Reset a day to re-run it
python main.py campaign reset 5

# Revert a day to auto-generated schedule
python main.py campaign edit-day 5 --revert
```

## 30-day schedule

The campaign runs in 4 phases, automatically generated from your `campaign.toml`:

| Phase | Days | Activity | Goal |
|-------|------|----------|------|
| 1 | 1–8 | Karma building only | Build account credibility |
| 2 | 9–15 | Karma + light seeding | Start natural product mentions |
| 3 | 16–22 | Seeding + first posts | Begin content posting |
| 4 | 23–30 | Full campaign | Posts + seeding + monitoring |

### Task types

| Task | Description |
|------|-------------|
| **KARMA** | Helpful comments on target subs (no product mention) |
| **SEED** | Naturally mention your product in relevant discussions |
| **POST** | Submit a post to a subreddit |
| **MONITOR** | Check existing posts for new comments |
| **REST** | No activity |
| **REVIEW** | Collect metrics + review performance |

## Safety features

- **Pre-flight checks** — Account health, daily limits, and timing grade before every action
- **Daily limits** — Configurable max posts and comments per day
- **Random delays** — 90–180s between actions to avoid bot detection
- **Timing blocks** — Automatically avoids low-traffic hours (EST night)
- **Duplicate prevention** — Skips already-commented posts and already-posted subreddits
- **3-level comment fallback** — JS injection → CDP retry → full page reload retry

## Project structure

```
├── extension/                 # Chrome extension
│   ├── manifest.json
│   ├── background.js          # Service Worker (WebSocket + CDP)
│   ├── popup.html/js          # Extension popup UI
│   └── record-content.js      # Content script
├── src/
│   ├── cli.py                 # Click CLI
│   ├── autopilot_browser.py   # Browser automation orchestrator
│   ├── pi_browser_client.py   # WebSocket server (extension communication)
│   ├── pi_browser.py          # Reddit browser actions
│   ├── marketing/engine.py    # Marketing engine (safety checks/limits)
│   ├── schedule.py            # 30-day schedule generator
│   ├── comment_generator.py   # AI comment generation (kimi CLI)
│   ├── state.py               # SQLite state management
│   └── display.py             # Rich terminal UI
├── main.py                    # Entry point
├── campaign.example.toml      # Campaign config template
└── pyproject.toml             # Dependencies
```

## Documentation

- [Usage Guide](docs/USAGE.md) — Detailed setup and command reference
- [Architecture](docs/ARCHITECTURE.md) — Module structure, data flow, DB schema

## Disclaimer

This tool is for educational and personal marketing purposes. Use responsibly and in compliance with [Reddit's Terms of Service](https://www.redditinc.com/policies/user-agreement). The authors are not responsible for any account actions resulting from use of this tool.

## License

[MIT](LICENSE)
