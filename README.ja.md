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

### 2. Taskのインストール（任意だが推奨）

より簡単なプロジェクト管理のために、Task runnerをインストールしてください：

```bash
# miseを使用する場合（miseがインストールされている場合）
mise install task=latest

# または https://taskfile.dev/installation/ から直接インストール
```

### 3. 環境変数の設定（必須 - dotenvxの使用）

セキュリティと適切な設定のために、**dotenvxの使用が必須**です：

1. [dotenvx.com](https://dotenvx.com/) からdotenvxをインストール：
```bash
# https://dotenvx.com/ のインストール手順に従ってください
# 例：Linux/macOSの場合：
curl -fsSL https://dotenvx.sh/ | sh
```

2. 例ファイルをコピー：
```bash
cp .env.example .env
```

3. `.env`を編集して必要な変数をアンコメント/変更：
```bash
# Discord webhook用
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your/webhook/url"

# テスト中に通知を無効化する場合
DISCORD_NOTIFIER_DISABLED="false"
```

4. dotenvxを使用してアプリケーションを実行：
```bash
dotenvx up  # 環境変数をロード
dotenvx exec "python3 fetch_openrouter.py"  # ロードされた変数で実行
```

**重要**: アプリケーションはdotenvxで動作するように設計されています。dotenvxを使わずに `python3 fetch_openrouter.py` を直接実行すると、設定が不足する可能性があります。
```

### 4. Taskを使用したセットアップ（推奨）

Taskがインストールされている場合、単に実行：
```bash
task setup
```

これにより以下の処理が行われます：
- 仮想環境の作成
- 依存関係のインストール
- 必要なディレクトリとファイルの作成
- データベースの初期化

### 5. 手動セットアップ（代替）

Taskを使用したくない場合は、手動でセットアップできます：

1. 仮想環境を作成：
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows
```

2. 依存関係をインストール：
```bash
pip install -r requirements.txt
```

3. 設定ファイルの編集

`config.yaml`を編集して、Discord Webhook URLを設定します（環境変数を使用しない場合）。

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
  base_url: "https://r.jina.ai/https://openrouter.ai/models?fmt=table&max_price=0&order=top-weekly"
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

4. データベースを初期化：
```bash
python3 -c "from db import Database; db = Database('models.db'); db.__enter__(); db.init_db()"
```

## 使用方法

### Taskを使用（推奨）

Taskがインストールされている場合、これらの便利なコマンドを使用できます：

```bash
# メインスクリプトを実行
task run

# テストを実行
task test

# 特定のテストを実行
task test-unit
task test-format
task test-discord

# コードのリンティングとフォーマット
task lint
task lint-fix

# 一時ファイルをクリーンアップ
task clean
task clean-logs
task clean-db
task reset

# プロジェクトの状態を確認
task status

# 利用可能なタスクを表示
task help
```

### 手動実行

```bash
./venv/bin/python3 fetch_openrouter.py
```

### 自動実行 (Cron)

Cronを使用して1日2回（例: 午前6時と午後6時）実行するように設定します。

Taskを使用（推奨）：
```bash
0 6 * * * cd /path/to/openrouter-tracker && task run
0 18 * * * cd /path/to/openrouter-tracker && task run
```

または直接Python実行：
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
