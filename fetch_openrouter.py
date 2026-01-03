#!/usr/bin/env python3
import logging
import re
import time
from datetime import datetime
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
import yaml

from db import DailyStats
from db import Database
from db import Model
from discord_notifier import DiscordNotifier

# Constant definitions
BASE_DIR = Path(__file__).parent.resolve()

# Pattern definitions (for table format Markdown)
# Table row pattern (non-greedy matching for long lines)
TABLE_ROW_PATTERN = r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|"
# Model URL pattern: [Model Name](https://openrouter.ai/provider/model-id)
MODEL_URL_PATTERN = r"\[(.*?)\]\(https://openrouter\.ai/[^/]+/(.*?)\)"


def setup_logging(config: dict):
    """Set up logging"""
    log_file = Path(config["logging"]["file"])

    # Resolve to absolute path
    if not log_file.is_absolute():
        log_file = BASE_DIR / log_file

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config["logging"]["level"]))

    # Clear existing handlers
    logger.handlers.clear()

    # File handler (with rotation)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config["logging"]["max_size_mb"] * 1024 * 1024,
        backupCount=config["logging"]["backup_count"],
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
    )
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    return logger


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration file"""
    # Load config file with absolute path
    abs_config_path = BASE_DIR / config_path

    with open(abs_config_path) as f:
        config = yaml.safe_load(f)

    # Convert relative paths to absolute paths (only if paths in config are relative)
    db_path = Path(config["database"]["path"])
    if not db_path.is_absolute():
        config["database"]["path"] = str(BASE_DIR / db_path)

    log_path = Path(config["logging"]["file"])
    if not log_path.is_absolute():
        config["logging"]["file"] = str(BASE_DIR / log_path)

    return config


def normalize_tokens(tokens_str: str) -> float:
    """Normalize token string (convert M/B to numbers)"""
    tokens_str = tokens_str.strip().upper()
    tokens_str = tokens_str.replace(",", "")
    tokens_str = tokens_str.replace("TOKENS", "")

    if tokens_str.endswith("B"):
        return float(tokens_str[:-1]) * 1000
    elif tokens_str.endswith("M"):
        return float(tokens_str[:-1])
    else:
        return float(tokens_str)


def normalize_context(context_str: str) -> int:
    """Normalize context length string (convert K to number)"""
    context_str = context_str.strip()
    if context_str.endswith("K"):
        return int(context_str[:-1]) * 1024
    else:
        return int(context_str)


def extract_price(price_str: str) -> float:
    """Extract number from price string (e.g., "$0.0001/M" → 0.0001)"""
    if not price_str:
        return 0.0

    price_str = price_str.strip()
    # Remove $ symbol
    price_str = price_str.replace("$", "")
    # Remove /M
    price_str = price_str.replace("/M", "")

    try:
        return float(price_str)
    except ValueError:
        return 0.0


def fetch_markdown(config: dict, logger: logging.Logger) -> str:
    """Fetch Markdown data from r.jina.ai"""
    max_retries = config["api"]["max_retries"]
    retry_delay = config["api"]["retry_delay"]
    last_error = None

    # Set headers
    headers = {"User-Agent": config["api"]["user_agent"]}

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                config["api"]["base_url"],
                timeout=config["api"]["timeout"],
                headers=headers,
            )
            response.raise_for_status()

            if not response.text.strip():
                error_msg = "Empty response from API"
                raise ValueError(error_msg)

            return response.text

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                sleep_time = retry_delay * (attempt + 1)
                logger.warning(
                    "Attempt %d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    e,
                    sleep_time,
                )
                time.sleep(sleep_time)
            else:
                error_msg = f"Failed to fetch data after {max_retries + 1} attempts"
                logger.error(error_msg)
                error_msg = f"Failed after {max_retries + 1} attempts: {last_error}"
                raise RuntimeError(error_msg) from last_error


def parse_markdown(markdown: str, logger: logging.Logger) -> list[dict]:
    """Parse table format Markdown to extract model information"""
    models = []
    rank_counter = 0

    # Process line by line
    lines = markdown.split("\n")

    # Skip table header
    in_table = False
    header_line_count = 0

    for line in lines:
        # Detect table start (header line) - line containing Model Name & ID
        # or Model Name
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
                    r"https://openrouter\.ai/[^/]+/(.*?)", model_name_col
                )
                if url_match:
                    model_id = url_match.group(1)
                    # Remove URL from model name
                    clean_name = re.sub(
                        r"https://openrouter\.ai/[^/]+/.*?\s*", "", model_name_col
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

            # Weekly token count cannot be obtained directly from API, so set
            # rank based on line number
            # API sorts models by order=top-weekly, so line number becomes the rank
            # Here we set a temporary value and overwrite with actual rank later
            rank_counter += 1
            # API returns models in top-weekly order, so rank_counter becomes the rank
            # Use inverse of rank as weekly token count (lower rank = more tokens)
            weekly_tokens = (
                10000.0 / rank_counter
            )  # Temporary value, higher rank has smaller value

            models.append(
                {
                    "id": model_id,
                    "name": clean_name,
                    "provider": provider,
                    "context_length": context_length,
                    "description": "",
                    "weekly_tokens": weekly_tokens,
                    "prompt_price": input_price,
                    "completion_price": output_price,
                }
            )

    if not models:
        logger.error("No models found in table markdown data")
        error_msg = "Failed to parse models from table markdown"
        raise ValueError(error_msg)

    logger.info("Parsed %d models", len(models))
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

        # Sort by weekly token count to create rankings (commented out)
        models_data.sort(key=lambda x: x["weekly_tokens"], reverse=True)

        # Database operations
        db_path = Path(config["database"]["path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        new_models = []

        with Database(str(db_path)) as db:
            # Initialize database
            db.init_db()

            # Detect new models (check before upsert)
            existing_ids = db.get_all_model_ids()
            current_ids = {m["id"] for m in models_data}
            new_model_ids = current_ids - existing_ids

            # Extract new model information
            new_models = [m for m in models_data if m["id"] in new_model_ids]

            if new_models:
                logger.info("Detected %d new models", len(new_models))

            # Save model information
            for model_data in models_data:
                model = Model(
                    id=model_data["id"],
                    name=model_data["name"],
                    provider=model_data["provider"],
                    context_length=model_data["context_length"],
                    description="",
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat(),
                )
                db.upsert_model(model)

            # Save daily statistics
            today = datetime.now().strftime("%Y-%m-%d")
            daily_stats = []
            for rank, model_data in enumerate(models_data, 1):
                stat = DailyStats(
                    model_id=model_data["id"],
                    date=today,
                    rank=rank,
                    weekly_tokens=model_data["weekly_tokens"],
                    prompt_price=model_data["prompt_price"],
                    completion_price=model_data["completion_price"],
                )
                daily_stats.append(stat)

            db.save_daily_stats(daily_stats)
            logger.info("Saved %d daily stats", len(daily_stats))

        # Discord notifications
        notifier = DiscordNotifier(
            webhook_url=config["discord"]["webhook_url"],
            enabled=config["discord"]["enabled"],
        )

        # Get previous day's rankings (compare with most recent data from 24+ hours ago)
        # If today is 2026-01-02, get the latest data from before 2026-01-01
        threshold_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

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
        total_tokens = sum(m["weekly_tokens"] for m in models_data)

        notifier.send_summary(
            total_models=len(models_data),
            total_tokens=total_tokens,
            new_models_count=len(new_models),
        )

        logger.info("Execution completed successfully")

    except Exception as e:
        logger.exception("Error during execution: %s", e)
        # If notifications are enabled, could send error notification, but
        # here we just log
        raise


if __name__ == "__main__":
    main()
