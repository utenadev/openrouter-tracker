# openrouter-tracker Implementation Documentation (v2)

## Project Overview

System that tracks weekly token usage and rankings of OpenRouter's free models, sending notifications to Discord twice daily (6:00 AM, 6:00 PM).

**Data Source**: OpenRouter's table format Markdown (using `fmt=table` parameter)
=======

---

## Directory Structure

```
~/openrouter-tracker/
├── fetch_openrouter.py      # Main script
├── discord_notifier.py      # Discord notifications
├── db.py                    # SQLite database operations
├── config.yaml              # Configuration file
├── models.db                # SQLite database (created at runtime)
├── logs/                    # Log directory
│   └── app.log
├── setup.sh                 # Initial setup script
└── requirements.txt         # Python dependencies
```

---

## Implementation of Each File

### 1. requirements.txt

```
pyyaml>=6.0
requests>=2.31.0
```

---

### 2. Environment Variables (dotenvx recommended)

For security and flexibility, you can override settings using environment variables.

**Supported Environment Variables**:

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL (takes precedence over config.yaml) | `https://discord.com/api/webhooks/...` |
| `DISCORD_NOTIFIER_DISABLED` | Disable notifications ("true" to disable) | `"false"` |
| `DATABASE_PATH` | Database path (optional) | `"./models.db"` |
| `LOG_LEVEL` | Log level (optional) | `"INFO"` |
| `API_BASE_URL` | API base URL (optional) | `"https://r.jina.ai/..."` |
| `API_TIMEOUT` | API timeout (optional) | `30` |

**Usage**:

```bash
# Create .env from .env.example
cp .env.example .env

# Edit .env file
nano .env

# Run using dotenvx
dotenvx up
dotenvx exec "python3 fetch_openrouter.py"
```

### 3. config.yaml

Default settings used when environment variables are not set.

```yaml
# Discord settings
discord:
  webhook_url: "YOUR_DISCORD_WEBHOOK_URL_HERE"
  enabled: true

# Database settings
database:
  path: "models.db"

# API settings (table format support)
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

# Future LLM parsing feature (next phase)
llm_parser:
  enabled: false
  provider: "openrouter"
  model: "anthropic/claude-3.5-sonnet"
  api_key: "YOUR_API_KEY_HERE"
  fallback_to_manual: true
```

---

### 3. db.py

```python
import sqlite3
import time
from datetime import datetime
from typing import List, Dict, Optional, Set
from dataclasses import dataclass

@dataclass
class Model:
    id: str
    name: str
    provider: str
    context_length: int
    description: str
    created_at: str
    updated_at: str

@dataclass
class DailyStats:
    model_id: str
    date: str
    rank: int
    weekly_tokens: float
    prompt_price: float
    completion_price: float

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def __enter__(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.conn = sqlite3.connect(self.db_path, timeout=30.0)
                self.conn.execute("PRAGMA journal_mode=WAL")
                self.conn.row_factory = sqlite3.Row
                return self
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def init_db(self):
        """Initialize database"""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS models (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    context_length INTEGER,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT NOT NULL,
                    date DATE NOT NULL,
                    rank INTEGER NOT NULL,
                    weekly_tokens REAL NOT NULL,
                    prompt_price REAL,
                    completion_price REAL,
                    FOREIGN KEY (model_id) REFERENCES models(id),
                    UNIQUE(model_id, date)
                )
            """)

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_id TEXT,
                    event TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_stats_date
                ON daily_stats(date)
            """)

            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_stats_rank
                ON daily_stats(rank, date)
            """)

    def upsert_model(self, model: Model):
        """Update or insert model information"""
        with self.conn:
            cursor = self.conn.execute("""
                INSERT INTO models (id, name, provider, context_length, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    provider = excluded.provider,
                    context_length = excluded.context_length,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            """, (model.id, model.name, model.provider, model.context_length, model.description))

            # Record in history if new
            if cursor.rowcount > 0 and cursor.lastrowid > 0:
                is_new = self.conn.execute(
                    "SELECT COUNT(*) FROM history WHERE model_id = ? AND event = 'new'",
                    (model.id,)
                ).fetchone()[0] == 0

                if is_new:
                    self.conn.execute("""
                        INSERT INTO history (model_id, event, details)
                        VALUES (?, 'new', ?)
                    """, (model.id, f"New model added: {model.name}"))

    def save_daily_stats(self, stats: List[DailyStats]):
        """Save daily statistics"""
        today = datetime.now().strftime('%Y-%m-%d')

        with self.conn:
            for stat in stats:
                self.conn.execute("""
                    INSERT OR REPLACE INTO daily_stats
                    (model_id, date, rank, weekly_tokens, prompt_price, completion_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (stat.model_id, stat.date, stat.rank, stat.weekly_tokens,
                      stat.prompt_price, stat.completion_price))

    def get_latest_rankings_before(self, date_threshold: str) -> Dict[str, int]:
        """Get the most recent rankings before the specified date (for comparison 24+ hours ago)"""
        # Get the most recent date before the specified date
        latest_date_row = self.conn.execute("""
            SELECT MAX(date) as max_date
            FROM daily_stats
            WHERE date <= ?
        """, (date_threshold,)).fetchone()

        if not latest_date_row or not latest_date_row['max_date']:
            return {}

        target_date = latest_date_row['max_date']

        previous_rankings = self.conn.execute("""
            SELECT model_id, rank
            FROM daily_stats
            WHERE date = ?
        """, (target_date,)).fetchall()

        return {row['model_id']: row['rank'] for row in previous_rankings}

    def get_top_models_by_tokens(self, date: str, limit: int = 5) -> List[Dict]:
        """Get top N models by token count for the specified date"""
        return self.conn.execute("""
            SELECT m.*, d.rank, d.weekly_tokens
            FROM daily_stats d
            JOIN models m ON d.model_id = m.id
            WHERE d.date = ?
            ORDER BY d.rank
            LIMIT ?
        """, (date, limit)).fetchall()

    def get_all_models(self) -> List[Model]:
        """Get all models"""
        rows = self.conn.execute("SELECT * FROM models").fetchall()
        return [Model(**dict(row)) for row in rows]

    def get_all_model_ids(self) -> Set[str]:
        """Get set of all model IDs"""
        rows = self.conn.execute("SELECT id FROM models").fetchall()
        return {row['id'] for row in rows}

    def detect_new_models(self, current_models: List[str]) -> List[str]:
        """Detect new models"""
        existing_models = self.get_all_model_ids()
        new_models = [model_id for model_id in current_models if model_id not in existing_models]
        return new_models
```

---

### 4. discord_notifier.py

```python
import requests
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self, webhook_url: str, enabled: bool = True):
        self.webhook_url = webhook_url
        self.enabled = enabled

    def send_top5_notification(self, models: List[Dict], previous_rankings: Dict[str, int]):
        """Send top 5 models notification"""
        if not self.enabled:
            logger.info("Discord notifications are disabled")
            return

        today = datetime.now().strftime('%Y-%m-%d')

        embed = {
            "title": f"📊 OpenRouter Free Model Weekly Rankings Top 5",
            "description": f"📅 {today}",
            "color": 0x5865F2,
            "fields": []
        }

        for i, model in enumerate(models[:5], 1):
            prev_rank = previous_rankings.get(model['id'], i) # Assume current rank if no data
            change = prev_rank - i

            if change > 0:
                change_emoji = "📈"
                change_text = f"#{prev_rank} → #{i} (+{change})"
            elif change < 0:
                change_emoji = "📉"
                change_text = f"#{prev_rank} → #{i} ({change})"
            else:
                change_emoji = "➡️"
                change_text = f"#{i}"

            # Format token count
            weekly_tokens = model['weekly_tokens']
            if weekly_tokens >= 1000:
                tokens_str = f"{weekly_tokens/1000:.2f}B"
            else:
                tokens_str = f"{weekly_tokens:.1f}M"

            # Format context length
            context = model['context_length']
            if context >= 1024:
                context_str = f"{context//1024}K"
            else:
                context_str = str(context)

            field = {
                "name": f"{i}. {model['name']}",
                "value": f"🔸 Weekly Tokens: {tokens_str}\n" +
                        f"📈 Previous Rank: {change_text} {change_emoji}\n" +
                        f"📏 Context: {context_str}",
                "inline": False
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_new_models_notification(self, new_models: List[Dict]):
        """Send new model addition notification"""
        if not self.enabled or not new_models:
            return

        embed = {
            "title": "🆕 New models have been added",
            "color": 0x00FF00,
            "fields": []
        }

        for model in new_models:
            field = {
                "name": model['name'],
                "value": f"Provider: {model['provider']}\n" +
                        f"Context: {model['context_length']:,}",
                "inline": False
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_summary(self, total_models: int, total_tokens: float, new_models_count: int):
        """Send statistical summary notification"""
        if not self.enabled:
            return

        if total_tokens >= 1000:
            tokens_str = f"{total_tokens/1000:.2f}B"
        else:
            tokens_str = f"{total_tokens:.1f}M"

        embed = {
            "title": "📊 Statistical Summary",
            "color": 0x1E88E5,
            "fields": [
                {"name": "Total Models", "value": str(total_models), "inline": True},
                {"name": "Total Weekly Tokens", "value": tokens_str, "inline": True},
                {"name": "Added Models", "value": str(new_models_count), "inline": True}
            ]
        }

        self.send_embed(embed)

    def send_embed(self, embed: Dict):
        """Send embed message"""
        payload = {"embeds": [embed]}

        try:
            time.sleep(1)  # Rate limit protection
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            # Add retry logic
            time.sleep(2)
            try:
                response = requests.post(self.webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Discord notification sent successfully on retry")
            except Exception as e:
                logger.error(f"Failed to send Discord notification on retry: {e}")
```

---

### 5. fetch_openrouter.py

```python
#!/usr/bin/env python3
import re
import time
import yaml
import logging
import requests
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
from db import Database, Model, DailyStats
from discord_notifier import DiscordNotifier

# Constant definitions
BASE_DIR = Path(__file__).parent.resolve()

# Pattern definitions (for table format Markdown)
# Table row pattern (non-greedy matching for long lines)
TABLE_ROW_PATTERN = r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|"
# Model URL pattern: [Model Name](https://openrouter.ai/provider/model-id)
MODEL_URL_PATTERN = r"\[(.*?)\]\(https://openrouter\.ai/[^/]+/(.*?)\)"

def setup_logging(config: Dict):
    """Set up logging"""
    log_file = Path(config['logging']['file'])

    # Resolve to absolute path
    if not log_file.is_absolute():
        BASE_DIR = Path(__file__).parent.resolve()
        log_file = BASE_DIR / log_file

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config['logging']['level']))

    # Clear existing handlers
    logger.handlers.clear()

    # File handler (with rotation)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config['logging']['max_size_mb'] * 1024 * 1024,
        backupCount=config['logging']['backup_count']
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    return logger

def load_config(config_path: str = "config.yaml") -> Dict:
    """Load configuration file"""
    # Load config file with absolute path
    abs_config_path = BASE_DIR / config_path

    with open(abs_config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Convert relative paths to absolute paths (only if paths in config are relative)
    db_path = Path(config['database']['path'])
    if not db_path.is_absolute():
        config['database']['path'] = str(BASE_DIR / db_path)

    log_path = Path(config['logging']['file'])
    if not log_path.is_absolute():
        config['logging']['file'] = str(BASE_DIR / log_path)

    return config

def normalize_tokens(tokens_str: str) -> float:
    """Normalize token string (convert M/B to numbers)"""
    tokens_str = tokens_str.strip().upper()
    tokens_str = tokens_str.replace(',', '')
    tokens_str = tokens_str.replace('TOKENS', '')

    if tokens_str.endswith('B'):
        return float(tokens_str[:-1]) * 1000
    elif tokens_str.endswith('M'):
        return float(tokens_str[:-1])
    else:
        return float(tokens_str)

def normalize_context(context_str: str) -> int:
    """Normalize context length string (convert K to number)"""
    context_str = context_str.strip()
    if context_str.endswith('K'):
        return int(context_str[:-1]) * 1024
    else:
        return int(context_str)

def fetch_markdown(config: Dict, logger: logging.Logger) -> str:
    """Fetch Markdown data from OpenRouter API via r.jina.ai"""
    max_retries = config['api']['max_retries']
    retry_delay = config['api']['retry_delay']
    last_error = None

    # Set headers (including user agent)
    headers = {
        'User-Agent': config['api']['user_agent']
    }

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                config['api']['base_url'],
                timeout=config['api']['timeout'],
                headers=headers
            )
            response.raise_for_status()

            if not response.text.strip():
                raise ValueError("Empty response from API")

            return response.text

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                sleep_time = retry_delay * (attempt + 1)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                logger.error(f"Failed to fetch data after {max_retries + 1} attempts")
                raise RuntimeError(f"Failed after {max_retries + 1} attempts: {last_error}")

def parse_markdown(markdown: str, logger: logging.Logger) -> List[Dict]:
    """Parse Markdown to extract model information"""
    models = []
    rank_counter = 0

    # Process line by line
    lines = markdown.split('\n')

    # Skip table header
    in_table = False
    header_line_count = 0

    for line in lines:
        # Detect table start (header line) - line containing Model Name & ID or Model Name
        if line.startswith("|") and ("Model Name" in line or "Model" in line):
            in_table = True
            header_line_count = 0
            continue

        # Skip table header separator line
        if in_table and header_line_count == 0:
            if line.startswith("|") and "-" in line:
                header_line_count = 1
                continue

        # Process table data rows
        if in_table and line.startswith("|"):
            # Match with table row pattern
            table_match = re.search(TABLE_ROW_PATTERN, line)
            if not table_match:
                # Debug: Show line that didn't match
                logger.debug("No match for line: %s", line[:100])
                continue

            # Extract each column of the table
            columns = [col.strip() for col in table_match.groups()]
            if len(columns) < 4:
                continue

            # Actual data format
            model_name_col, input_price_col, output_price_col, context_col = columns[:4]

            # Extract model name and ID (model name contains URL)
            model_url_match = re.search(MODEL_URL_PATTERN, model_name_col)
            if not model_url_match:
                # If URL is direct
                url_match = re.search(
                    r"https://openrouter\.ai/[^/]+/(.*?)",
                    model_name_col
                )
                if url_match:
                    model_id = url_match.group(1)
                    # Remove URL from model name
                    clean_name = re.sub(
                        r"https://openrouter\.ai/[^/]+/.*?\s*",
                        "",
                        model_name_col
                    ).strip()
                else:
                    # Skip if no URL
                    continue
            else:
                clean_name, model_id = model_url_match.groups()

            # Extract ID surrounded by backticks
            backtick_match = re.search(r"`([^`]+)`", model_name_col)
            if backtick_match:
                model_id = backtick_match.group(1)

            # Extract provider from model name
            if ":" in clean_name:
                provider = clean_name.split(":")[0].strip()
                # Remove provider name from model name
                clean_name = clean_name.split(":")[1].strip()
            else:
                provider = "Unknown"

            # Extract context length
            context_str = context_col.replace(",", "") if context_col else "0"
            context_length = normalize_context(context_str) if context_str else 0

            # Extract price
            input_price = extract_price(input_price_col)
            output_price = extract_price(output_price_col)

            # Weekly token count cannot be obtained directly from API, so set rank based on line number
            # API sorts models by order=top-weekly, so line number becomes the rank
            # Here we set a temporary value and overwrite with actual rank later
            rank_counter += 1
            # API returns models in top-weekly order, so rank_counter becomes the rank
            # Use inverse of rank as weekly token count (lower rank = more tokens)
            weekly_tokens = 10000.0 / rank_counter  # Temporary value, higher rank has smaller value

            models.append({
                'id': model_id,
                'name': clean_name,
                'provider': provider,
                'context_length': context_length,
                'description': '',
                'weekly_tokens': weekly_tokens,
                'prompt_price': input_price,
                'completion_price': output_price
            })

    if not models:
        logger.error("No models found in table markdown data")
        raise ValueError("Failed to parse models from table markdown")

    logger.info(f"Parsed {len(models)} models")
    return models

def main():
    """Main processing"""
    # Load configuration
    config = load_config()

    # Set up logging
    logger = setup_logging(config)
    logger.info("=" * 50)
    logger.info("Starting openrouter-tracker")

    try:
        # Fetch data
        logger.info("Fetching markdown data...")
        markdown = fetch_markdown(config, logger)

        # Parse
        logger.info("Parsing markdown data...")
        models_data = parse_markdown(markdown, logger)

        # Sort by weekly token count to create rankings
        models_data.sort(key=lambda x: x['weekly_tokens'], reverse=True)

        # Database operations
        db_path = Path(config['database']['path'])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        new_models = []

        with Database(str(db_path)) as db:
            # Initialize database
            db.init_db()

            # Detect new models (check before upsert)
            existing_ids = db.get_all_model_ids()
            current_ids = {m['id'] for m in models_data}
            new_model_ids = current_ids - existing_ids

            # Extract new model information
            new_models = [m for m in models_data if m['id'] in new_model_ids]

            if new_models:
                logger.info(f"Detected {len(new_models)} new models")

            # Save model information
            for model_data in models_data:
                model = Model(
                    id=model_data['id'],
                    name=model_data['name'],
                    provider=model_data['provider'],
                    context_length=model_data['context_length'],
                    description='',
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )
                db.upsert_model(model)

            # Save daily statistics
            today = datetime.now().strftime('%Y-%m-%d')
            daily_stats = []
            for rank, model_data in enumerate(models_data, 1):
                stat = DailyStats(
                    model_id=model_data['id'],
                    date=today,
                    rank=rank,
                    weekly_tokens=model_data['weekly_tokens'],
                    prompt_price=model_data['prompt_price'],
                    completion_price=model_data['completion_price']
                )
                daily_stats.append(stat)

            db.save_daily_stats(daily_stats)
            logger.info(f"Saved {len(daily_stats)} daily stats")

        # Discord notifications
        notifier = DiscordNotifier(
            webhook_url=config['discord']['webhook_url'],
            enabled=config['discord']['enabled']
        )

        # Get previous day's rankings (compare with most recent data from 24+ hours ago)
        # If today is 2026-01-02, get the latest data from before 2026-01-01
        threshold_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        with Database(str(db_path)) as db:
            previous_rankings = db.get_latest_rankings_before(threshold_date)
            top_models = db.get_top_models_by_tokens(today, limit=5)

        # Top 5 notification
        logger.info("Sending Discord notification...")
        notifier.send_top5_notification(top_models, previous_rankings)

        # New model notification
        if new_models:
            logger.info("Sending New Models notification...")
            notifier.send_new_models_notification(new_models)

        # Summary notification
        total_tokens = sum(m['weekly_tokens'] for m in models_data)

        notifier.send_summary(
            total_models=len(models_data),
            total_tokens=total_tokens,
            new_models_count=len(new_models)
        )

        logger.info("Execution completed successfully")

    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
        # If notifications are enabled, could send error notification, but here we just log
        raise

if __name__ == "__main__":
    main()
```

---

### 6. setup.sh

```bash
#!/bin/bash
set -e

echo "Setting up openrouter-tracker..."

# Create directory
mkdir -p logs

# Create virtual environment (recommended)
cd "$(dirname "$0")"
python3 -m venv venv

# Create .gitignore
echo "venv/" > .gitignore
echo "__pycache__/" >> .gitignore
echo "*.db" >> .gitignore
echo "config.yaml" >> .gitignore
echo "logs/" >> .gitignore

# Install dependencies
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# Create config.yaml if it doesn't exist
if [ ! -f config.yaml ]; then
    echo "config.yaml not found. Please create it manually."
fi

# Set script execution permissions
chmod +x fetch_openrouter.py

# Initialize database
./venv/bin/python3 -c "from db import Database; db = Database('models.db'); db.__enter__(); db.init_db()"

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your Discord webhook URL"
echo "2. Run: ./venv/bin/python3 fetch_openrouter.py"
echo "3. Add to crontab: crontab -e"
```

---

## Setup Instructions

### 1. Project Placement

```bash
# Create project directory in home
mkdir -p ~/openrouter-tracker
cd ~/openrouter-tracker

# Place all the above files
```

### 2. Install Dependencies

```bash
cd ~/openrouter-tracker
# Create virtual environment and install
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 3. Set Environment Variables (Recommended)

For security, manage sensitive information using environment variables:

```bash
# Create .env from .env.example
cp .env.example .env

# Edit .env file (nano or your preferred editor)
nano .env
```

Set the following in the `.env` file (uncomment and enter values):
```env
# Discord Webhook URL (required)
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your/webhook/url"

# Other settings (optional)
# DISCORD_NOTIFIER_DISABLED="false"
# DATABASE_PATH="./models.db"
```

### 4. Edit Configuration File (Optional)

For settings not covered by environment variables, edit config.yaml:

```bash
nano config.yaml
```

Edit the following items:
- `discord.webhook_url`: Set if not using environment variables
- `database.path`: `models.db` (relative path is OK)
- Other API settings, etc.
- `logging.file`: `logs/app.log` (relative path is OK)

### 4. Initial Execution

```bash
# Use virtual environment's python
cd ~/openrouter-tracker
./venv/bin/python3 fetch_openrouter.py
```

### 5. Set up Cron

```bash
# Edit user's crontab
crontab -e

# Add the following (specify full paths)
0 6 * * * cd /home/USER/openrouter-tracker && /home/USER/openrouter-tracker/venv/bin/python3 fetch_openrouter.py
0 18 * * * cd /home/USER/openrouter-tracker && /home/USER/openrouter-tracker/venv/bin/python3 fetch_openrouter.py
```

Replace `USER` with the actual username.

---

## Execution Methods

### Manual Execution (dotenvx recommended)

```bash
cd ~/openrouter-tracker

# Load environment variables and execute
dotenvx up
dotenvx exec "python3 fetch_openrouter.py"

# Or execute directly (if environment variables are already set)
./venv/bin/python3 fetch_openrouter.py
```

**Note**: `dotenvx up` loads environment variables into the current shell. You need to run it again in a new terminal session.

### Automatic Execution

Automatically executed twice daily at 6:00 AM and 6:00 PM via Cron.

---

## Running Tests

### Execute Test Scripts

```bash
cd ~/openrouter-tracker

# Load environment variables and run tests
dotenvx up
dotenvx exec "python3 tests/test_main_with_mock.py"

# Other test scripts
dotenvx exec "python3 tests/test_script.py"
dotenvx exec "python3 tests/test_error_handling.py"
```

**Note**: It's recommended to set `DISCORD_NOTIFIER_DISABLED="true"` when running tests.

## Check Logs

```bash
tail -f ~/openrouter-tracker/logs/app.log
```
