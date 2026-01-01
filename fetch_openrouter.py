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

# 定数定義
BASE_DIR = Path(__file__).parent.resolve()

# パターン定義
MODEL_PATTERN = r'\*   \[(.*?)\]\(https://openrouter\.ai/[^)]+\)\s+(\d+\.?\d*[MB]?) tokens'
CONTEXT_PATTERN = r'(\d+K?) context'
PRICE_INPUT_PATTERN = r'\$(\d+\.?\d*)/M input tokens'
PRICE_OUTPUT_PATTERN = r'\$(\d+\.?\d*)/M output tokens'
PROVIDER_PATTERN = r'by \[(.*?)\]'

def setup_logging(config: Dict):
    """ログ設定"""
    log_file = Path(config['logging']['file'])
    
    # 絶対パスに解決
    if not log_file.is_absolute():
        log_file = BASE_DIR / log_file
        
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config['logging']['level']))

    # 既存のハンドラーをクリア
    logger.handlers.clear()

    # ファイルハンドラー（ローテーション付き）
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

    # コンソールハンドラー
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    return logger

def load_config(config_path: str = "config.yaml") -> Dict:
    """設定ファイルの読み込み"""
    # 絶対パスでconfigファイルを読み込む
    abs_config_path = BASE_DIR / config_path
    
    with open(abs_config_path, 'r') as f:
        config = yaml.safe_load(f)

    # 相対パスを絶対パスに変換（configに書かれたパスが相対パスの場合のみ）
    db_path = Path(config['database']['path'])
    if not db_path.is_absolute():
        config['database']['path'] = str(BASE_DIR / db_path)
        
    log_path = Path(config['logging']['file'])
    if not log_path.is_absolute():
        config['logging']['file'] = str(BASE_DIR / log_path)

    return config

def normalize_tokens(tokens_str: str) -> float:
    """トークン文字列を正規化（M/Bを数値に変換）"""
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
    """コンテキスト長文字列を正規化（Kを数値に変換）"""
    context_str = context_str.strip()
    if context_str.endswith('K'):
        return int(context_str[:-1]) * 1024
    else:
        return int(context_str)

def fetch_markdown(config: Dict, logger: logging.Logger) -> str:
    """r.jina.aiからMarkdownデータを取得"""
    max_retries = config['api']['max_retries']
    retry_delay = config['api']['retry_delay']
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                config['api']['base_url'],
                timeout=config['api']['timeout']
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
    """Markdownをパースしてモデル情報を抽出"""
    models = []

    # 各モデルエントリを抽出
    model_entries = re.findall(MODEL_PATTERN, markdown)

    if not model_entries:
        logger.error("No models found in markdown data")
        raise ValueError("Failed to parse models from markdown")

    for i, match in enumerate(model_entries):
        name, url, tokens = match
        model_id = url.split('openrouter.ai/')[-1]

        # コンテキスト長を抽出
        context_match = re.search(CONTEXT_PATTERN, markdown)
        context_length = normalize_context(context_match.group(1)) if context_match else 0

        # プロバイダーを抽出
        provider_match = re.search(PROVIDER_PATTERN, markdown)
        provider = provider_match.group(1) if provider_match else "Unknown"

        # 価格を抽出
        input_price_match = re.search(PRICE_INPUT_PATTERN, markdown)
        input_price = float(input_price_match.group(1)) if input_price_match else 0.0

        output_price_match = re.search(PRICE_OUTPUT_PATTERN, markdown)
        output_price = float(output_price_match.group(1)) if output_price_match else 0.0

        models.append({
            'id': model_id,
            'name': name,
            'provider': provider,
            'context_length': context_length,
            'description': '',
            'weekly_tokens': normalize_tokens(tokens),
            'prompt_price': input_price,
            'completion_price': output_price
        })

    logger.info(f"Parsed {len(models)} models")
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
        models_data.sort(key=lambda x: x['weekly_tokens'], reverse=True)

        # データベース操作
        db_path = Path(config['database']['path'])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        new_models = []
        
        with Database(str(db_path)) as db:
            # データベース初期化
            db.init_db()

            # 新規モデル検出（Upsert前にチェック）
            existing_ids = db.get_all_model_ids()
            current_ids = {m['id'] for m in models_data}
            new_model_ids = current_ids - existing_ids
            
            # 新規モデルの情報を抽出
            new_models = [m for m in models_data if m['id'] in new_model_ids]
            
            if new_models:
                logger.info(f"Detected {len(new_models)} new models")

            # モデル情報を保存
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

            # 日次統計を保存
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

        # Discord通知
        notifier = DiscordNotifier(
            webhook_url=config['discord']['webhook_url'],
            enabled=config['discord']['enabled']
        )

        # 前日の順位を取得 (24時間以上前の直近のデータと比較)
        # 本日が 2026-01-02 なら、2026-01-01 以前の最新データを取得
        threshold_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
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
        total_tokens = sum(m['weekly_tokens'] for m in models_data)
        
        notifier.send_summary(
            total_models=len(models_data),
            total_tokens=total_tokens,
            new_models_count=len(new_models)
        )

        logger.info("Execution completed successfully")

    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
        # 通知が有効ならエラー通知を飛ばしても良いが、ここではログ出力にとどめる
        raise

if __name__ == "__main__":
    main()