# OpenRouter Tracker

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

OpenRouterの無料モデルの使用統計とランキングを追跡するためのPythonベースのユーティリティです。

## 概要

OpenRouter Trackerは、OpenRouterから（`r.jina.ai`経由で）データを取得し、ローカルのSQLiteデータベースに保存して、日次レポートをDiscordチャンネルに送信します。

## 主な機能

* **データ取得**: 週間トークン使用量、コンテキスト長、価格などのモデルデータをスクレイピングします。
* **データベース**: モデル情報と日次統計をSQLite (`models.db`) に保存します。
* **通知**: 以下のDiscord通知を送信します：
  * 週間トークン使用量によるトップ5モデル。
  * 新規モデルの追加。
  * 日次サマリー。
* **ロギング**: ローテーションサポート付きの詳細なロギング。

## 必要条件

* Python 3.11以上
* SQLite 3
* Discord Webhook URL

## セットアップ

### 1. リポジトリのクローン

```bash
git clone https://github.com/utenadev/openrouter-tracker.git
cd openrouter-tracker
```

### 2. 依存関係のインストール

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 3. 設定ファイルの編集

`config.yaml`を編集して、Discord Webhook URLを設定します。

```yaml
# Discord設定
discord:
  webhook_url: "YOUR_DISCORD_WEBHOOK_URL_HERE"
  enabled: true

# データベース設定
database:
  path: "models.db"

# API設定
api:
  base_url: "https://r.jina.ai/https://openrouter.ai/models?max_price=0&order=top-weekly"
  timeout: 30
  max_retries: 2
  retry_delay: 5
  user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# ログ設定
logging:
  file: "logs/app.log"
  level: "INFO"
  max_size_mb: 10
  backup_count: 5
```

### 4. セットアップスクリプトの実行

```bash
chmod +x setup.sh
./setup.sh
```

## 使用方法

### 手動実行

```bash
./venv/bin/python3 fetch_openrouter.py
```

### 自動実行 (Cron)

Cronを使用して1日2回（例: 午前6時と午後6時）実行するように設定します。

```bash
0 6 * * * cd /path/to/openrouter-tracker && /path/to/venv/bin/python3 fetch_openrouter.py
0 18 * * * cd /path/to/openrouter-tracker && /path/to/venv/bin/python3 fetch_openrouter.py
```

## ディレクトリ構成

```
openrouter-tracker/
├── config.yaml          # 設定ファイル
├── db.py                # データベース操作
├── discord_notifier.py  # Discord通知
├── fetch_openrouter.py  # メインスクリプト
├── requirements.txt     # 依存関係
├── setup.sh             # セットアップスクリプト
├── LICENSE              # ライセンス
├── README.ja.md         # 日本語README
├── docs/                # ドキュメント
│   ├── FEATURE_TODO.md  # 将来的な機能
│   ├── factcheck_20260101_geminicli+gemini3.md  # ファクトチェックレポート
│   ├── openrouter-tracker_IMPLEMENTATION.md  # 実装ドキュメント
│   ├── openrouter-tracker_IMPLEMENTATION_NOTES.md  # 実装メモ
│   └── review_20260101_geminicli+gemini3.md  # レビューレポート
└── tests/               # テスト
    ├── check_database.py  # データベース確認
    ├── debug_fetch.py      # デバッグ用
    ├── debug_pattern.py    # パターンデバッグ
    ├── fetch_openrouter_json.py  # JSON取得テスト
    ├── test_error_handling.py  # エラーハンドリングテスト
    ├── test_limit.py        # limitテスト
    ├── test_main_with_mock.py  # メインテスト
    └── test_script.py       # スクリプトテスト
```

## テスト

テストを実行するには、以下のコマンドを使用します。

```bash
# 単体テスト
./venv/bin/python3 tests/test_script.py

# メインテスト（モックデータ）
./venv/bin/python3 tests/test_main_with_mock.py

# エラーハンドリングテスト
./venv/bin/python3 -m unittest tests.test_error_handling
```

## ライセンス

このプロジェクトはMITライセンスの下で提供されています。詳細については、[LICENSE](LICENSE)ファイルを参照してください。

## 貢献

貢献は歓迎します。プルリクエストを送信する前に、イシューを作成して議論してください。

## 作者

* **OpenRouter Tracker** - [utenadev](https://github.com/utenadev)

## 更新履歴

* 2026-01-01: 初版リリース
