#!/usr/bin/env python3
import logging
import re
import time
from datetime import datetime
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict
from typing import List

import requests
import yaml

from db import DailyStats
from db import Database
from db import Model
from discord_notifier import DiscordNotifier

# 定数定義
BASE_DIR = Path(__file__).parent.resolve()

# パターン定義(テーブル形式Markdown用)
# テーブル行パターン(非貪欲マッチングで長い行に対応)
TABLE_ROW_PATTERN = r"\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|"
# モデルURLパターン: [Model Name](https://openrouter.ai/provider/model-id)
MODEL_URL_PATTERN = r"\[(.*?)\]\(https://openrouter\.ai/[^/]+/(.*?)\)"

def setup_logging(config: Dict):
    """ログ設定"""
    log_file = Path(config["logging"]["file"])

    # 絶対パスに解決
    if not log_file.is_absolute():
        log_file = BASE_DIR / log_file

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config["logging"]["level"]))

    # 既存のハンドラーをクリア
    logger.handlers.clear()

    # ファイルハンドラー(ローテーション付き)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config["logging"]["max_size_mb"] * 1024 * 1024,
        backupCount=config["logging"]["backup_count"]
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)

    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    return logger

def load_config(config_path: str = "config.yaml") -> Dict:
    """設定ファイルの読み込み"""
    # 絶対パスでconfigファイルを読み込む
    abs_config_path = BASE_DIR / config_path

    with open(abs_config_path) as f:
        config = yaml.safe_load(f)

    # 相対パスを絶対パスに変換(configに書かれたパスが相対パスの場合のみ)
    db_path = Path(config["database"]["path"])
    if not db_path.is_absolute():
        config["database"]["path"] = str(BASE_DIR / db_path)

    log_path = Path(config["logging"]["file"])
    if not log_path.is_absolute():
        config["logging"]["file"] = str(BASE_DIR / log_path)

    return config

def normalize_tokens(tokens_str: str) -> float:
    """トークン文字列を正規化(M/Bを数値に変換)"""
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
    """コンテキスト長文字列を正規化(Kを数値に変換)"""
    context_str = context_str.strip()
    if context_str.endswith("K"):
        return int(context_str[:-1]) * 1024
    else:
        return int(context_str)

def extract_price(price_str: str) -> float:
    """価格文字列から数値を抽出(例: "$0.0001/M" → 0.0001)"""
    if not price_str:
        return 0.0

    price_str = price_str.strip()
    # $記号を削除
    price_str = price_str.replace("$", "")
    # /Mを削除
    price_str = price_str.replace("/M", "")

    try:
        return float(price_str)
    except ValueError:
        return 0.0

def fetch_markdown(config: Dict, logger: logging.Logger) -> str:
    """r.jina.aiからMarkdownデータを取得"""
    max_retries = config["api"]["max_retries"]
    retry_delay = config["api"]["retry_delay"]
    last_error = None

    # ヘッダーの設定
    headers = {
        "User-Agent": config["api"]["user_agent"]
    }

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                config["api"]["base_url"],
                timeout=config["api"]["timeout"],
                headers=headers
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
                    attempt + 1, e, sleep_time
                )
                time.sleep(sleep_time)
            else:
                error_msg = f"Failed to fetch data after {max_retries + 1} attempts"
                logger.error(error_msg)
                error_msg = f"Failed after {max_retries + 1} attempts: {last_error}"
                raise RuntimeError(error_msg) from last_error

def parse_markdown(markdown: str, logger: logging.Logger) -> List[Dict]:
    """テーブル形式Markdownをパースしてモデル情報を抽出"""
    models = []

    # 行ごとに処理
    lines = markdown.split("\n")

    # テーブルヘッダーをスキップ
    in_table = False
    header_line_count = 0

    for line in lines:
        # テーブルの開始を検出(ヘッダー行) - Model Name & IDまたはModel Nameを含む行
        if line.startswith("|") and ("Model Name" in line or "Model" in line):
            in_table = True
            header_line_count = 0
            continue

        # テーブルヘッダーのセパレーター行をスキップ
        if in_table and header_line_count == 0:
            if line.startswith("|") and "-" in line:
                header_line_count = 1
                continue

        # テーブルデータ行を処理
        if in_table and line.startswith("|"):
            # テーブル行パターンでマッチ
            table_match = re.search(TABLE_ROW_PATTERN, line)
            if not table_match:
                # デバッグ: マッチしなかった行を表示
                logger.debug("No match for line: %s", line[:100])
                continue

            # テーブルの各列を抽出
            columns = [col.strip() for col in table_match.groups()]
            if len(columns) < 4:
                continue

            # 実際のデータ形式
            model_name_col, input_price_col, output_price_col, context_col = columns[:4]

            # モデル名とIDを抽出(モデル名にはURLが含まれる)
            model_url_match = re.search(MODEL_URL_PATTERN, model_name_col)
            if not model_url_match:
                # URLが直接の場合
                url_match = re.search(
                    r"https://openrouter\.ai/[^/]+/(.*?)",
                    model_name_col
                )
                if url_match:
                    model_id = url_match.group(1)
                    # モデル名からURLを除去
                    clean_name = re.sub(
                        r"https://openrouter\.ai/[^/]+/.*?\s*",
                        "",
                        model_name_col
                    ).strip()
                else:
                    # URLがない場合はスキップ
                    continue
            else:
                clean_name, model_id = model_url_match.groups()

            # バックティックで囲まれたIDを抽出
            backtick_match = re.search(r"`([^`]+)`", model_name_col)
            if backtick_match:
                model_id = backtick_match.group(1)

            # プロバイダーをモデル名から抽出
            if ":" in clean_name:
                provider = clean_name.split(":")[0].strip()
                # モデル名からプロバイダー名を除去
                clean_name = clean_name.split(":")[1].strip()
            else:
                provider = "Unknown"

            # コンテキスト長を抽出
            context_str = context_col.replace(",", "") if context_col else "0"
            context_length = normalize_context(context_str) if context_str else 0

            # 価格を抽出
            input_price = extract_price(input_price_col)
            output_price = extract_price(output_price_col)

            # 周間トークン数はAPIから取得できないため、デフォルト値を設定
            # 実際の実装では、別の方法で取得する必要があります
            weekly_tokens = 0.0  # デフォルト値

            models.append({
                "id": model_id,
                "name": clean_name,
                "provider": provider,
                "context_length": context_length,
                "description": "",
                "weekly_tokens": weekly_tokens,
                "prompt_price": input_price,
                "completion_price": output_price
            })

    if not models:
        logger.error("No models found in table markdown data")
        error_msg = "Failed to parse models from table markdown"
        raise ValueError(error_msg)

    logger.info("Parsed %d models", len(models))
    return models

def main():
    """メイン処理"""
    # 設定読み込み
    config = load_config()

    # ログ設定
    logger = setup_logging(config)
    logger.info("=" * 50)
    logger.info("Starting openrouter-tracker")

    try:
        # データ取得
        logger.info("Fetching markdown data...")
        markdown = fetch_markdown(config, logger)

        # パース
        logger.info("Parsing markdown data...")
        models_data = parse_markdown(markdown, logger)

        # 週間トークン数でソートしてランキング作成
        models_data.sort(key=lambda x: x["weekly_tokens"], reverse=True)

        # データベース操作
        db_path = Path(config["database"]["path"])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        new_models = []

        with Database(str(db_path)) as db:
            # データベース初期化
            db.init_db()

            # 新規モデル検出(Upsert前にチェック)
            existing_ids = db.get_all_model_ids()
            current_ids = {m["id"] for m in models_data}
            new_model_ids = current_ids - existing_ids

            # 新規モデルの情報を抽出
            new_models = [m for m in models_data if m["id"] in new_model_ids]

            if new_models:
                logger.info("Detected %d new models", len(new_models))

            # モデル情報を保存
            for model_data in models_data:
                model = Model(
                    id=model_data["id"],
                    name=model_data["name"],
                    provider=model_data["provider"],
                    context_length=model_data["context_length"],
                    description="",
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat()
                )
                db.upsert_model(model)

            # 日次統計を保存
            today = datetime.now().strftime("%Y-%m-%d")
            daily_stats = []
            for rank, model_data in enumerate(models_data, 1):
                stat = DailyStats(
                    model_id=model_data["id"],
                    date=today,
                    rank=rank,
                    weekly_tokens=model_data["weekly_tokens"],
                    prompt_price=model_data["prompt_price"],
                    completion_price=model_data["completion_price"]
                )
                daily_stats.append(stat)

            db.save_daily_stats(daily_stats)
            logger.info("Saved %d daily stats", len(daily_stats))

        # Discord通知
        notifier = DiscordNotifier(
            webhook_url=config["discord"]["webhook_url"],
            enabled=config["discord"]["enabled"]
        )

        # 前日の順位を取得 (24時間以上前の直近のデータと比較)
        # 本日が 2026-01-02 なら、2026-01-01 以前の最新データを取得
        threshold_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with Database(str(db_path)) as db:
            previous_rankings = db.get_latest_rankings_before(threshold_date)
            top_models = db.get_top_models_by_tokens(today, limit=5)

        # トップ5通知
        logger.info("Sending Discord notification...")
        notifier.send_top5_notification(top_models, previous_rankings)

        # 新規モデル通知
        if new_models:
            logger.info("Sending New Models notification...")
            notifier.send_new_models_notification(new_models)

        # サマリー通知
        total_tokens = sum(m["weekly_tokens"] for m in models_data)

        notifier.send_summary(
            total_models=len(models_data),
            total_tokens=total_tokens,
            new_models_count=len(new_models)
        )

        logger.info("Execution completed successfully")

    except Exception as e:
        logger.exception("Error during execution: %s", e)
        # 通知が有効ならエラー通知を飛ばしても良いが、ここではログ出力にとどめる
        raise

if __name__ == "__main__":
    main()
