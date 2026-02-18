# Web Traffic Bot

A Python + Selenium bot for personal website **load testing** and **traffic simulation**.  
It opens real browser sessions, scrolls through pages, and simulates user engagement — useful for testing Google Analytics, CDN behaviour, and server load.

---

## Features

- Headless Chrome/Chromium sessions via Selenium
- Configurable number of sessions, session duration, and total run time
- Optional proxy rotation (round-robin)
- Randomised user-agent rotation
- Realistic engagement simulation (scrolling, mouse movement, idle time)
- YAML config file **or** pure CLI flags
- Installable as a system command (`web-traffic-bot`)

---

## Requirements

- Python 3.8+
- Google Chrome or Chromium
- `chromedriver` (auto-managed by `webdriver-manager`)

### Ubuntu / Debian quick setup

```bash
bash scripts/ubuntu_setup.sh
```

---

## Installation

```bash
# Clone the repo
git clone https://github.com/<your-username>/web-traffic-bot.git
cd web-traffic-bot

# (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install the package and its dependencies
pip install -e .
```

After installation the `web-traffic-bot` command is available in your shell.

---

## Usage

### Via CLI flags (no config file needed)

```bash
web-traffic-bot --url https://yoursite.com --sessions 20 --duration 600
```

### Via YAML config file

```bash
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml to suit your needs
web-traffic-bot --config config/config.yaml
```

### Mix both (CLI flags override config file values)

```bash
web-traffic-bot --config config/config.yaml --sessions 50 --no-headless
```

### All options

```
usage: web-traffic-bot [-h] [--url URL] [--config CONFIG]
                       [--sessions SESSIONS] [--duration DURATION]
                       [--session-duration SESSION_DURATION]
                       [--headless] [--no-headless]
                       [--proxy PROXY_URL]

Options:
  --url, --target-url   Target URL to test
  --config, -c          Path to YAML config file
  --sessions            Number of sessions to run (default: 10)
  --duration            Total run duration in seconds (default: 600)
  --session-duration    Duration per session in seconds (default: 45)
  --headless            Run in headless mode (default)
  --no-headless         Run with a visible browser window
  --proxy PROXY_URL     Proxy URL; repeat for multiple proxies
                        e.g. --proxy http://user:pass@host:port
```

---

## Configuration file reference

```yaml
# config/config.yaml
target_url: "https://yoursite.com"
sessions_count: 10          # number of browser sessions
session_duration: 45        # seconds each session stays on the page
duration_seconds: 600       # hard stop after this many seconds total
proxies:
  - "http://user:password@proxy1.example:8000"
  - "http://user:password@proxy2.example:8000"
headless: true
chromium_path: ""           # leave blank to auto-detect via webdriver-manager
```

---

## Running directly (without installing)

```bash
python -m bot.cli --url https://yoursite.com --sessions 5
```

---

## Project structure

```
web-traffic-bot/
├── bot/
│   ├── __init__.py
│   ├── config_handler.py   # YAML config loader + attribute accessors
│   ├── logger.py           # Logging setup
│   ├── proxy_manager.py    # Round-robin proxy rotation
│   ├── selenium_driver.py  # Chrome/Chromium WebDriver wrapper
│   ├── session_simulator.py# Realistic engagement simulation
│   ├── traffic_bot.py      # Main orchestrator
│   └── cli/
│       ├── __init__.py
│       └── __main__.py     # CLI entry point
├── config/
│   └── config.example.yaml
├── scripts/
│   └── ubuntu_setup.sh
├── requirements.txt
├── setup.py
└── README.md
```

---

## Disclaimer

This tool is intended **only for testing your own websites**.  
Do not use it against websites you do not own or have explicit permission to test.
