# OpenRouter Tracker

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Python-based utility to track OpenRouter's free model usage statistics and rankings.

## Overview

OpenRouter Tracker fetches data from OpenRouter (via `r.jina.ai`), stores it in a local SQLite database, and sends daily reports to a Discord channel.

## Features

* **Data Fetching**: Scrapes model data from OpenRouter's table format including weekly token usage, context length, and pricing.
* **Database**: Stores model information and daily statistics in SQLite (`models.db`).
* **Notifications**: Sends Discord notifications for:
  * Top 5 models by weekly token usage.
  * New model additions.
  * Daily summaries.
* **Logging**: Detailed logging with rotation support.
* **Table Format Support**: Parses OpenRouter's new table-formatted markdown data.
* **Enhanced Error Handling**: Robust retry logic and error handling for API calls and database operations.
* **WAL Mode Database**: Uses SQLite WAL mode for better concurrency and performance.
* **Environment Variable Support**: Supports configuration via environment variables for better security.

## Requirements

* Python 3.11+
* SQLite 3
* Discord Webhook URL

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/utenadev/openrouter-tracker.git
cd openrouter-tracker
```

### 2. Install Task (Optional but Recommended)

For easier project management, install Task runner:

```bash
# Using mise (if you have mise installed)
mise install task=latest

# Or install directly from https://taskfile.dev/installation/
```

### 3. Set Up Environment Variables (Optional but Recommended)

For better security and flexibility, use environment variables with dotenvx:

1. Copy the example file:
```bash
cp .env.example .env
```

2. Edit `.env` and uncomment/modify the variables you need:
```bash
# For Discord webhook
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your/webhook/url"

# To disable notifications during testing
DISCORD_NOTIFIER_DISABLED="false"
```

3. Use dotenvx to run the application:
```bash
dotenvx up  # Load environment variables
dotenvx exec "python3 fetch_openrouter.py"  # Run with loaded variables
```

### 4. Setup Using Task (Recommended)

If you have Task installed, simply run:
```bash
task setup
```

This will:
- Create virtual environment
- Install dependencies
- Create necessary directories and files
- Initialize the database

### 5. Manual Setup (Alternative)

If you prefer not to use Task, you can set up manually:

1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Edit Configuration File

Edit `config.yaml` to set your Discord Webhook URL (if not using environment variables).

```yaml
# Discord settings
discord:
  webhook_url: "YOUR_DISCORD_WEBHOOK_URL_HERE"
  enabled: true

# Database settings
database:
  path: "models.db"

# API settings
api:
  base_url: "https://r.jina.ai/https://openrouter.ai/models?fmt=table&max_price=0&order=top-weekly"
  timeout: 30
  max_retries: 2
  retry_delay: 5
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# Logging settings
logging:
  file: "logs/app.log"
  level: "INFO"
  max_size_mb: 10
  backup_count: 5
```

4. Initialize the database:
```bash
python3 -c "from db import Database; db = Database('models.db'); db.__enter__(); db.init_db()"
```

## Usage

### Using Task (Recommended)

If you have Task installed, you can use these convenient commands:

```bash
# Run the main script
task run

# Run tests
task test

# Run specific tests
task test-unit
task test-format
task test-discord

# Lint and format code
task lint
task lint-fix

# Clean up temporary files
task clean
task clean-logs
task clean-db
task reset

# Check project status
task status

# Show available tasks
task help
```

### Manual Execution

```bash
./venv/bin/python3 fetch_openrouter.py
```

### Automatic Execution (Cron)

Set up Cron to run twice daily (e.g., 6:00 AM and 6:00 PM).

Using Task (recommended):
```bash
0 6 * * * cd /path/to/openrouter-tracker && task run
0 18 * * * cd /path/to/openrouter-tracker && task run
```

Or using direct Python execution:
```bash
0 6 * * * cd /path/to/openrouter-tracker && /path/to/venv/bin/python3 fetch_openrouter.py
0 18 * * * cd /path/to/openrouter-tracker && /path/to/venv/bin/python3 fetch_openrouter.py
```

## Directory Structure

```
openrouter-tracker/
├── config.yaml          # Configuration file
├── db.py                # Database operations
├── discord_notifier.py  # Discord notifications
├── fetch_openrouter.py  # Main script
├── requirements.txt     # Dependencies
├── setup.sh             # Setup script
├── LICENSE              # License
├── README.md            # README
├── README.ja.md         # Japanese README
├── docs/                # Documentation
│   ├── FEATURE_TODO.md  # Future features
│   ├── factcheck_20260101_geminicli+gemini3.md  # Fact check report
│   ├── openrouter-tracker_IMPLEMENTATION.md  # Implementation document
│   ├── openrouter-tracker_IMPLEMENTATION_NOTES.md  # Implementation notes
│   └── review_20260101_geminicli+gemini3.md  # Review report
└── tests/               # Tests
    ├── check_database.py  # Database check
    ├── debug_fetch.py      # Debug utility
    ├── debug_pattern.py    # Pattern debug
    ├── fetch_openrouter_json.py  # JSON fetch test
    ├── test_error_handling.py  # Error handling test
    ├── test_limit.py        # Limit test
    ├── test_main_with_mock.py  # Main test
    └── test_script.py       # Script test
```

## Tests

Run tests using the following commands:

```bash
# Unit tests
./venv/bin/python3 tests/test_script.py

# Main test (with mock data)
./venv/bin/python3 tests/test_main_with_mock.py

# Error handling test
./venv/bin/python3 -m unittest tests.test_error_handling
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome. Please create an issue to discuss before submitting a pull request.

## Authors

* **OpenRouter Tracker** - [utenadev](https://github.com/utenadev)

## Changelog

* 2026-01-01: Initial release
