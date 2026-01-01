# openrouter-tracker 実装ドキュメント

## プロジェクト概要

OpenRouterの無料モデルの週間トークン使用量とランキングを追跡し、毎日2回（6:00 AM, 6:00 PM）にDiscordへ通知するシステム。

---

## ディレクトリ構成

```
~/openrouter-tracker/
├── fetch_openrouter.py      # メインスクリプト
├── discord_notifier.py      # Discord通知
├── db.py                    # SQLiteデータベース操作
├── config.yaml              # 設定ファイル
├── models.db                # SQLiteデータベース（実行時に作成）
├── logs/                    # ログディレクトリ
│   └── app.log
├── setup.sh                 # 初期セットアップスクリプト
└── requirements.txt         # Python依存ライブラリ
```

---

## 各ファイルの実装

### 1. requirements.txt

```
pyyaml>=6.0
requests>=2.31.0
```

---

### 2. config.yaml

```yaml
# Discord設定
discord:
  webhook_url: "YOUR_DISCORD_WEBHOOK_URL_HERE"
  enabled: true

# データベース設定
database:
  path: "/home/USER/openrouter-tracker/models.db"

# API設定
api:
  base_url: "https://r.jina.ai/https://openrouter.ai/models?max_price=0"
  timeout: 30
  max_retries: 2
  retry_delay: 5

# ログ設定
logging:
  file: "/home/USER/openrouter-tracker/logs/app.log"
  level: "INFO"
  max_size_mb: 10
  backup_count: 5

# 将来的なLLM修正機能（次のフェーズ用）
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
from datetime import datetime
from typing import List, Dict, Optional
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
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def init_db(self):
        """データベースの初期化"""
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
        """モデル情報の更新または新規追加"""
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

            # 新規追加の場合、履歴に記録
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
        """日次統計を保存"""
        today = datetime.now().strftime('%Y-%m-%d')

        with self.conn:
            for stat in stats:
                self.conn.execute("""
                    INSERT OR REPLACE INTO daily_stats
                    (model_id, date, rank, weekly_tokens, prompt_price, completion_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (stat.model_id, stat.date, stat.rank, stat.weekly_tokens,
                      stat.prompt_price, stat.completion_price))

    def get_previous_rankings(self, date: str) -> Dict[str, int]:
        """前日の順位を取得"""
        previous_rankings = self.conn.execute("""
            SELECT model_id, rank
            FROM daily_stats
            WHERE date = ?
        """, (date,)).fetchall()

        return {row['model_id']: row['rank'] for row in previous_rankings}

    def get_top_models_by_tokens(self, date: str, limit: int = 5) -> List[Dict]:
        """指定日のトークン数トップNモデルを取得"""
        return self.conn.execute("""
            SELECT m.*, d.rank, d.weekly_tokens
            FROM daily_stats d
            JOIN models m ON d.model_id = m.id
            WHERE d.date = ?
            ORDER BY d.rank
            LIMIT ?
        """, (date, limit)).fetchall()

    def get_all_models(self) -> List[Model]:
        """全モデルを取得"""
        rows = self.conn.execute("SELECT * FROM models").fetchall()
        return [Model(**dict(row)) for row in rows]

    def detect_new_models(self, current_models: List[str]) -> List[str]:
        """新規モデルを検出"""
        existing_models = {row['id'] for row in self.conn.execute("SELECT id FROM models").fetchall()}
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
        """トップ5モデルの通知を送信"""
        if not self.enabled:
            logger.info("Discord notifications are disabled")
            return

        today = datetime.now().strftime('%Y-%m-%d')

        embed = {
            "title": f"📊 OpenRouter 無料モデル 週間ランキング Top 5",
            "description": f"📅 {today}",
            "color": 0x5865F2,
            "fields": []
        }

        for i, model in enumerate(models[:5], 1):
            prev_rank = previous_rankings.get(model['id'], i)
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

            # トークン数をフォーマット
            weekly_tokens = model['weekly_tokens']
            if weekly_tokens >= 1000:
                tokens_str = f"{weekly_tokens/1000:.2f}B"
            else:
                tokens_str = f"{weekly_tokens:.1f}M"

            # コンテキスト長をフォーマット
            context = model['context_length']
            if context >= 1024:
                context_str = f"{context//1024}K"
            else:
                context_str = str(context)

            field = {
                "name": f"{i}. {model['name']}",
                "value": f"🔸 週間トークン: {tokens_str}\n" +
                        f"📈 前日順位: {change_text} {change_emoji}\n" +
                        f"📏 コンテキスト: {context_str}",
                "inline": False
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_new_models_notification(self, new_models: List[Dict]):
        """新規追加モデルの通知"""
        if not self.enabled or not new_models:
            return

        embed = {
            "title": "🆕 新しいモデルが追加されました",
            "color": 0x00FF00,
            "fields": []
        }

        for model in new_models:
            field = {
                "name": model['name'],
                "value": f"プロバイダー: {model['provider']}\n" +
                        f"コンテキスト: {model['context_length']:,}",
                "inline": False
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_summary(self, total_models: int, total_tokens: float, new_models_count: int):
        """統計サマリーの通知"""
        if not self.enabled:
            return

        if total_tokens >= 1000:
            tokens_str = f"{total_tokens/1000:.2f}B"
        else:
            tokens_str = f"{total_tokens:.1f}M"

        embed = {
            "title": "📊 統計サマリー",
            "color": 0x1E88E5,
            "fields": [
                {"name": "総モデル数", "value": str(total_models), "inline": True},
                {"name": "今週の総トークン", "value": tokens_str, "inline": True},
                {"name": "追加されたモデル", "value": str(new_models_count), "inline": True}
            ]
        }

        self.send_embed(embed)

    def send_embed(self, embed: Dict):
        """埋め込みメッセージを送信"""
        payload = {"embeds": [embed]}

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
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

# パターン定義
MODEL_PATTERN = r'\*   \[(.*?)\]\((https://openrouter\.ai/[^)]+)\)\s+(\d+\.?\d*[MB]?) tokens'
CONTEXT_PATTERN = r'(\d+K?) context'
PRICE_INPUT_PATTERN = r'\$(\d+\.?\d*)/M input tokens'
PRICE_OUTPUT_PATTERN = r'\$(\d+\.?\d*)/M output tokens'
PROVIDER_PATTERN = r'by \[(.*?)\]'

def setup_logging(config: Dict):
    """ログ設定"""
    log_file = Path(config['logging']['file'])
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
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # 相対パスを絶対パスに変換
    BASE_DIR = Path(__file__).parent.resolve()
    config['database']['path'] = str(BASE_DIR / "models.db")
    config['logging']['file'] = str(BASE_DIR / "logs" / "app.log")

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

        with Database(str(db_path)) as db:
            # データベース初期化
            db.init_db()

            # モデル情報を保存
            for model_data in models_data:
                model = Model(
                    id=model_data['id'],
                    name=model_data['name'],
                    provider=model_data['provider'],
                    context_length=model_data['context_length'],
                    description=model_data['description'],
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

        # 前日の順位を取得
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        with Database(str(db_path)) as db:
            previous_rankings = db.get_previous_rankings(yesterday)
            top_models = db.get_top_models_by_tokens(today, limit=5)

        # トップ5通知
        logger.info("Sending Discord notification...")
        notifier.send_top5_notification(top_models, previous_rankings)

        # サマリー通知
        total_tokens = sum(m['weekly_tokens'] for m in models_data)
        new_models_count = 0

        notifier.send_summary(
            total_models=len(models_data),
            total_tokens=total_tokens,
            new_models_count=new_models_count
        )

        logger.info("Execution completed successfully")

    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)
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

# ディレクトリ作成
mkdir -p ~/openrouter-tracker/logs

# 仮想環境の作成（推奨）
cd ~/openrouter-tracker
python3 -m venv venv
source venv/bin/activate

# 依存ライブラリのインストール
pip install --upgrade pip
pip install -r requirements.txt

# config.yamlの作成（まだ存在しない場合）
if [ ! -f config.yaml ]; then
    echo "config.yaml not found. Please create it manually."
fi

# スクリプトの実行権限設定
chmod +x fetch_openrouter.py

# データベースの初期化
python3 -c "from db import Database; db = Database('models.db'); db.__enter__(); db.init_db()"

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your Discord webhook URL"
echo "2. Run: python3 fetch_openrouter.py"
echo "3. Add to crontab: crontab -e"
```

---

## セットアップ手順

### 1. プロジェクトの配置

```bash
# ホームディレクトリにプロジェクトディレクトリを作成
mkdir -p ~/openrouter-tracker
cd ~/openrouter-tracker

# 上記のファイルをすべて配置
```

### 2. 依存ライブラリのインストール

```bash
cd ~/openrouter-tracker
pip3 install -r requirements.txt
```

または、仮想環境を使用する場合：

```bash
cd ~/openrouter-tracker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 設定ファイルの編集

```bash
nano config.yaml
```

以下の項目を編集：
- `discord.webhook_url`: 実際のDiscord Webhook URLに置換
- `database.path`: ユーザー名を含めたフルパスに更新
- `logging.file`: ユーザー名を含めたフルパスに更新

### 4. 初期実行

```bash
# 仮想環境を使用している場合
cd ~/openrouter-tracker
source venv/bin/activate
python3 fetch_openrouter.py

# または、直接実行
python3 ~/openrouter-tracker/fetch_openrouter.py
```

### 5. Cronの設定

```bash
# ユーザーのcrontabを編集
crontab -e

# 以下を追加（仮想環境を使用する場合）
0 6 * * * cd /home/USER/openrouter-tracker && /home/USER/openrouter-tracker/venv/bin/python fetch_openrouter.py
0 18 * * * cd /home/USER/openrouter-tracker && /home/USER/openrouter-tracker/venv/bin/python fetch_openrouter.py

# 仮想環境を使用しない場合
0 6 * * * /usr/bin/python3 /home/USER/openrouter-tracker/fetch_openrouter.py
0 18 * * * /usr/bin/python3 /home/USER/openrouter-tracker/fetch_openrouter.py
```

※ `USER` の部分を実際のユーザー名に置換してください。

---

## 実行方法

### 手動実行

```bash
cd ~/openrouter-tracker
source venv/bin/activate
python3 fetch_openrouter.py
```

### 自動実行

Cronにより、毎日 6:00 AM と 6:00 PM に自動実行されます。

---

## ログの確認

```bash
tail -f ~/openrouter-tracker/logs/app.log
```

---

## 次のフェーズ: LLMパーサーの実装

### 機能概要

r.jina.ai のフォーマット変更に対応するため、LLMを使用してパターンを自動学習・修正する機能。

### 実装予定ファイル

- `llm_parser.py`: LLMを使用したパーサー
- `patterns.yaml`: 学習したパターンを保存するファイル
- 更新版 `fetch_openrouter.py`: LLMパーサーを統合

### 処理フロー

1. 通常の正規表現パースを試行
2. 失敗した場合、LLMを呼び出して新しいパターンを抽出
3. LLMが抽出したパターンで再度パース
4. 成功したパターンを `patterns.yaml` に保存
5. 次回実行時は保存されたパターンを優先使用

### 使用するLLM

デフォルト: `anthropic/claude-3.5-sonnet`（OpenRouter経由）

---

## トラブルシューティング

### Discord通知が届かない

1. `config.yaml` の `discord.enabled` を確認
2. Webhook URLが正しいか確認
3. ログを確認: `tail -f ~/openrouter-tracker/logs/app.log`

### データ取得に失敗する

1. r.jina.ai サービスが稼働しているか確認
2. インターネット接続を確認
3. タイムアウト設定を確認（デフォルト: 30秒）

### Cronが実行されない

1. `crontab -l` でcronエントリを確認
2. システムログを確認: `grep CRON /var/log/syslog`
3. パスが正しいか確認

---

## Raspberry Pi 3での注意点

- メモリ使用量: 約30MB
- 実行時間: 約3-5秒
- ディスク使用量: 約10MB/月
