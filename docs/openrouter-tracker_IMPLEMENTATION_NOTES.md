# openrouter-tracker 実装メモ

## 概要

このドキュメントは、実際にシステムを実装する際の注意点、実装ポイント、テスト方法などをまとめたものです。

---

## ディレクトリ構成（任意の場所に配置）

```
<任意のディレクトリ>/openrouter-tracker/
├── fetch_openrouter.py      # メインスクリプト
├── discord_notifier.py      # Discord通知
├── db.py                    # SQLiteデータベース操作
├── config.yaml              # 設定ファイル
├── models.db                # SQLiteデータベース（実行時に作成）
├── logs/                    # ログディレクトリ
│   └── app.log
├── setup.sh                 # 初期セットアップスクリプト
├── requirements.txt         # Python依存ライブラリ
└── IMPLEMENTATION_NOTES.md  # このドキュメント
```

---

## 重要な実装ポイント

### 1. config.yaml のパス処理

**注意点**: config.yaml にパスを記述する場合、絶対パスを推奨します。以下の2つのアプローチがあります：

**アプローチA: config.yaml に絶対パスを記述**
```yaml
database:
  path: "/home/username/openrouter-tracker/models.db"

logging:
  file: "/home/username/openrouter-tracker/logs/app.log"
```

**アプローチB: スクリプト内で相対パスを絶対パスに変換**
```python
# fetch_openrouter.py
import pathlib

BASE_DIR = pathlib.Path(__file__).parent.resolve()

# config.yamlの値を上書き
config['database']['path'] = str(BASE_DIR / "models.db")
config['logging']['file'] = str(BASE_DIR / "logs" / "app.log")
```

**推奨**: アプローチBを採用すると、プロジェクトを任意の場所に配置しても動作します。

---

### 2. SQLiteの排他制御

**注意点**: Raspberry Piなどのリソース制限環境で、同時に複数のcronジョブが実行されるとSQLiteがロックされる可能性があります。

**解決策**:
```python
# db.py
import sqlite3
from contextlib import contextmanager

@contextmanager
def db_connection(db_path):
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)  # タイムアウトを延長
        conn.execute("PRAGMA journal_mode=WAL")  # WALモードで並列性向上
        conn.execute("PRAGMA busy_timeout=30000")
        yield conn
    finally:
        if conn:
            conn.close()
```

---

### 3. 正規表現のエッジケース

**注意点**: r.jina.ai の出力形式が変更される可能性があります。以下のエッジケースを考慮してください：

1. **トークン数のフォーマットバリエーション**:
   - `600M`, `2.94B`（現在）
   - `600M tokens`, `2.94B tokens`（スペース有り）
   - `600,000,000`, `2,940,000,000`（カンマ区切り）

2. **コンテキスト長のフォーマット**:
   - `4K`, `262K`（現在）
   - `4096`, `262144`（数値のみ）
   - `4k`（小文字）

**実装ポイント**:
```python
def normalize_tokens(tokens_str: str) -> float:
    """ロバストなトークン数正規化"""
    tokens_str = tokens_str.strip().upper()
    tokens_str = tokens_str.replace(',', '')  # カンマを削除
    tokens_str = tokens_str.replace('TOKENS', '')  # 単語を削除

    if tokens_str.endswith('B'):
        return float(tokens_str[:-1]) * 1000
    elif tokens_str.endswith('M'):
        return float(tokens_str[:-1])
    else:
        return float(tokens_str)
```

---

### 4. Discord Webhook のレート制限

**注意点**: DiscordのWebhookにはレート制限があり、短時間に大量のリクエストを送ると一時的にブロックされます。

**解決策**:
1. 複数の通知を1つの埋め込みメッセージにまとめる
2. 必要であれば遅延を入れる

**実装例**:
```python
# discord_notifier.py
import time

def send_multiple_embeds(embeds: List[Dict]):
    """複数の埋め込みメッセージを送信"""
    for i, embed in enumerate(embeds):
        self.send_embed(embed)
        if i < len(embeds) - 1:  # 最後以外は遅延
            time.sleep(1)
```

---

### 5. エラーハンドリングとリトライ

**重要**: 外部API（r.jina.ai）の呼び出しは必ずリトロジックを実装してください。

**実装ポイント**:
```python
def fetch_markdown(config: Dict, logger: logging.Logger) -> str:
    """r.jina.aiからMarkdownデータを取得（ロバスト版）"""
    max_retries = config['api']['max_retries']
    retry_delay = config['api']['retry_delay']

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                config['api']['base_url'],
                timeout=config['api']['timeout']
            )

            # HTTPエラーレスポンスも考慮
            response.raise_for_status()

            # 空のレスポンスをチェック
            if not response.text.strip():
                raise ValueError("Empty response from API")

            return response.text

        except requests.exceptions.Timeout as e:
            last_error = e
            logger.warning(f"Timeout on attempt {attempt + 1}: {e}")
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Request failed on attempt {attempt + 1}: {e}")
        except Exception as e:
            last_error = e
            logger.warning(f"Unexpected error on attempt {attempt + 1}: {e}")

        if attempt < max_retries:
            sleep_time = retry_delay * (attempt + 1)  # 指数バックオフ
            logger.info(f"Retrying in {sleep_time}s...")
            time.sleep(sleep_time)

    # 全てのリトライ失敗
    raise RuntimeError(f"Failed after {max_retries + 1} attempts. Last error: {last_error}")
```

---

### 6. ログのローテーション

**重要**: ログファイルが肥大化しないように、ローテーションを適切に設定してください。

**実装ポイント**:
```python
def setup_logging(config: Dict):
    """ログ設定（ローテーション付き）"""
    log_file = Path(config['logging']['file'])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config['logging']['level']))

    # 既存のハンドラーをクリア（重複を防ぐ）
    logger.handlers.clear()

    # ファイルハンドラー（ローテーション付き）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config['logging']['max_size_mb'] * 1024 * 1024,
        backupCount=config['logging']['backup_count'],
        encoding='utf-8'
    )

    # ログフォーマット
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # コンソールハンドラー（デバッグ用）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.WARNING)  # 警告以上のみコンソール出力
    logger.addHandler(console_handler)

    return logger
```

---

### 7. データベースの初期化

**注意点**: 初回実行時にデータベースを作成する必要があります。既存のデータを誤って削除しないように注意してください。

**実装ポイント**:
```python
def init_db(self):
    """データベースの初期化（冪等性確保）"""
    with self.conn:
        # テーブルが存在しない場合のみ作成
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

        # ... その他のテーブルも同様に ...

        # インデックスも同様に
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_daily_stats_date
            ON daily_stats(date)
        """)
```

---

### 8. 新規モデルの検出

**注意点**: 新規モデルが追加されたときに通知する必要があります。

**実装ポイント**:
```python
def detect_new_models(self, current_models: List[str]) -> List[str]:
    """新規モデルを検出"""
    existing_models = {row['id'] for row in self.conn.execute("SELECT id FROM models").fetchall()}
    new_models = [model_id for model_id in current_models if model_id not in existing_models]
    return new_models
```

---

### 9. 週間トークン数のランク計算

**注意点**: ランキングは週間トークン数に基づいて計算しますが、同順位のケースを考慮してください。

**実装ポイント**:
```python
def calculate_rankings(models: List[Dict]) -> List[Dict]:
    """週間トークン数に基づいてランキングを計算"""
    # トークン数で降順ソート
    sorted_models = sorted(models, key=lambda x: x['weekly_tokens'], reverse=True)

    # 同順位の処理（必要に応じて）
    for i, model in enumerate(sorted_models):
        model['rank'] = i + 1

    return sorted_models
```

---

## テスト方法

### 1. 単体テスト

**db.py のテスト**:
```python
# test_db.py
import unittest
from db import Database, Model

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.init_db()

    def test_upsert_model(self):
        model = Model(
            id="test/model:free",
            name="Test Model",
            provider="test",
            context_length=4096,
            description="Test description",
            created_at="2026-01-01",
            updated_at="2026-01-01"
        )
        self.db.upsert_model(model)

        result = self.db.conn.execute("SELECT * FROM models WHERE id = ?", (model.id,)).fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], model.name)

if __name__ == '__main__':
    unittest.main()
```

### 2. 統合テスト

**fetch_openrouter.py のテスト**:
```bash
# テスト用設定ファイル
cp config.yaml config.test.yaml
# config.test.yaml を編集（テスト用DBパス、Discord無効化など）

# テスト実行
python3 fetch_openrouter.py --config config.test.yaml
```

### 3. ローカルテスト

**手動テスト**:
```bash
# 1. 仮想環境作成
python3 -m venv venv
source venv/bin/activate

# 2. 依存インストール
pip install -r requirements.txt

# 3. 設定編集
nano config.yaml

# 4. 実行
python3 fetch_openrouter.py

# 5. ログ確認
tail -f logs/app.log

# 6. DB確認
sqlite3 models.db "SELECT * FROM models LIMIT 5;"
sqlite3 models.db "SELECT * FROM daily_stats ORDER BY date DESC LIMIT 5;"
```

---

## デバッグ方法

### 1. ログレベルの変更

```yaml
# config.yaml
logging:
  level: "DEBUG"  # INFO → DEBUGに変更
```

### 2. SQLiteの直接クエリ

```bash
# データベース接続
sqlite3 models.db

# テーブル一覧
.tables

# モデル一覧
SELECT id, name, provider, context_length FROM models;

# 今日の統計
SELECT m.name, d.rank, d.weekly_tokens
FROM daily_stats d
JOIN models m ON d.model_id = m.id
WHERE d.date = '2026-01-01'
ORDER BY d.rank;

# 履歴一覧
SELECT * FROM history ORDER BY timestamp DESC LIMIT 10;
```

### 3. APIレスポンスの保存

```python
# fetch_openrouter.py に追加
def fetch_markdown(config: Dict, logger: logging.Logger) -> str:
    markdown = # ... 既存の実装 ...

    # デバッグ用にレスポンスを保存
    debug_file = Path("debug/markdown_response.txt")
    debug_file.parent.mkdir(exist_ok=True)
    debug_file.write_text(markdown)

    return markdown
```

---

## Cron設定の注意点

### 1. 環境変数

**問題点**: Cron実行時はユーザーの `.bashrc` や `.zshrc` が読み込まれません。

**解決策**:
```bash
# crontab に環境変数を直接記述
PATH=/usr/local/bin:/usr/bin:/bin
HOME=/home/username

0 6 * * * cd /home/username/openrouter-tracker && /home/username/openrouter-tracker/venv/bin/python fetch_openrouter.py
```

### 2. 仮想環境のパス

**注意点**: 仮想環境を使用する場合、絶対パスを指定してください。

**推奨**:
```bash
# 絶対パスで指定
/home/username/openrouter-tracker/venv/bin/python /home/username/openrouter-tracker/fetch_openrouter.py
```

### 3. ログの出力先

**推奨**:
```bash
# アプリ側のロギングを使用する場合（推奨）
0 6 * * * cd /home/username/openrouter-tracker && /home/username/openrouter-tracker/venv/bin/python fetch_openrouter.py

# cron側のログファイルに保存する場合（デバッグ用）
0 6 * * * cd /home/username/openrouter-tracker && /home/username/openrouter-tracker/venv/bin/python fetch_openrouter.py >> /home/username/openrouter-tracker/logs/cron.log 2>&1
```

---

## セキュリティ上の注意点

### 1. config.yaml の権限

**推奨**:
```bash
chmod 600 config.yaml  # 所有者のみ読み書き可能
```

### 2. Discord Webhook URL の保護

**注意点**: Webhook URLは機密情報です。Gitなどにコミットしないでください。

**解決策**:
```bash
# .gitignore に追加
echo "config.yaml" >> .gitignore
```

### 3. APIキーの保護

**次のフェーズ（LLMパーサー）で必要になりますが、同様に保護してください。**

---

## 次のフェーズへの準備

### LLMパーサーの実装

**実装時に考慮すべき点**:

1. **パターン保存場所**: `patterns.yaml` に保存
2. **パターンのバージョン管理**: フォーマット変更を追跡
3. **フォールバック**: LLMパース失敗時の挙動
4. **コスト管理**: LLM APIの使用量を追跡

**実装ポイント**:
```python
# llm_parser.py（次のフェーズ用）

def load_patterns(patterns_file: str) -> Dict:
    """保存されたパターンを読み込み"""
    try:
        with open(patterns_file, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}

def save_patterns(patterns_file: str, patterns: Dict):
    """パターンを保存"""
    with open(patterns_file, 'w') as f:
        yaml.safe_dump(patterns, f)

def llm_assisted_parse(markdown: str, config: Dict) -> List[Dict]:
    """LLMを使用してパターンを学習・抽出"""
    # LLM API呼び出し
    # 新しいパターン抽出
    # patterns.yamlに保存
    # パース実行
    pass
```

---

## パフォーマンス最適化

### 1. SQLiteの最適化

```python
# db.py
def optimize_db(self):
    """データベースの最適化"""
    with self.conn:
        self.conn.execute("ANALYZE")
        self.conn.execute("VACUUM")
```

### 2. クエリの最適化

**インデックスの活用**:
```sql
-- よく使われるクエリにインデックスを作成
CREATE INDEX idx_daily_stats_model_date ON daily_stats(model_id, date);
```

### 3. メモリ使用量の最適化

```python
# 大量のデータを扱う場合、ジェネレーターを使用
def get_all_models_generator(self):
    """ジェネレーターで全モデルを取得"""
    cursor = self.conn.execute("SELECT * FROM models")
    while row := cursor.fetchone():
        yield Model(**dict(row))
```

---

## トラブルシューティングクイックリファレンス

| 問題 | 原因 | 解決策 |
|------|------|--------|
| Discord通知が届かない | Webhook URLが間違っている | config.yaml を確認 |
| データ取得失敗 | r.jina.aiダウン | 後で再試行 |
| SQLiteロックエラー | 同時に複数実行 | WALモード有効化、タイムアウト延長 |
| ログが肥大化 | ログローテーション未設定 | max_size_mb、backup_countを設定 |
| Cronが実行されない | パスが間違っている | 絶対パスを確認、パーミッション確認 |

---

## 追加の実装オプション

### 1. テストカバレッジの追加

```bash
# pytest インストール
pip install pytest pytest-cov

# テスト実行
pytest --cov=. --cov-report=html
```

### 2. Docker化

```dockerfile
# Dockerfile（オプション）
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "fetch_openrouter.py"]
```

### 3. ヘルスチェックエンドポイント

```python
# health.py（オプション）
def check_health():
    """システムの健全性チェック"""
    checks = {
        'database': check_db(),
        'api': check_api(),
        'discord': check_discord()
    }
    return checks
```

---

以上が実装メモです。このメモを参照しながら、実際の実装を進めてください。
