# OpenRouter Tracker コンテキスト

## プロジェクト概要
**OpenRouter Tracker** は、OpenRouterの無料モデルの使用統計とランキングを追跡するために設計されたPythonベースのユーティリティです。OpenRouterから（`r.jina.ai`経由で）データを取得し、ローカルのSQLiteデータベースに保存して、複数のDiscord通知を送信します。

## 主な機能
*   **データ取得**: OpenRouterのテーブル形式データから週間トークン使用量、コンテキスト長、入出力価格などのモデルデータをスクレイピングします。
*   **データベース**: モデル情報、日次統計、履歴イベントをSQLite (`models.db`) に保存します。
*   **通知**: 以下のDiscord通知を送信します：
    *   週間トークン使用量によるトップ5モデル（前日比較付き）。
    *   新規モデルの追加通知。
    *   統計サマリー（総モデル数、総トークン数、新規モデル数）。
*   **ロギング**: ローテーションサポート付きの詳細なロギング。
*   **エラー処理**: ネットワークリクエストのリトライロジックとDiscord通知のレート制限対策。
*   **テーブル形式対応**: OpenRouterの新しいテーブル形式Markdownに対応したパーサー。

## アーキテクチャと主要ファイル
*   `fetch_openrouter.py`: メインのエントリーポイント。取得、解析、データベース更新、通知を統括します。
*   `db.py`: すべてのSQLiteデータベース操作（スキーマ作成、Upsert、クエリ）を処理します。
*   `discord_notifier.py`: Discord Webhookの統合とメッセージフォーマットを管理します。
*   `config.yaml`: APIエンドポイント、データベースパス、ロギング、Discord認証情報の設定ファイルです。
*   `models.db`: SQLiteデータベースファイル（実行時に作成されます）。
*   `docs/`: 詳細な実装メモと仕様が含まれています。

## データベーススキーマ
プロジェクトは以下の3つのテーブルを使用します：

*   **models**: モデルの基本情報（ID、名前、プロバイダー、コンテキスト長、説明、作成日、更新日）
*   **daily_stats**: 日次統計（モデルID、日付、順位、週間トークン数、入力価格、出力価格）
*   **history**: モデルイベント履歴（モデルID、イベントタイプ、詳細、タイムスタンプ）

データベースはWAL（Write-Ahead Logging）モードで動作し、パフォーマンスと並行アクセスを最適化します。

## セットアップと設定

1.  **依存関係**:
    ```bash
    pip install -r requirements.txt
    ```
    必要なパッケージ: `pyyaml`, `requests`。

2.  **環境変数（dotenvx推奨）**:
    セキュリティと柔軟性のため、dotenvxを使用して環境変数を管理することを推奨します：

    ```bash
    # .env.exampleから.envを作成して編集
    cp .env.example .env
    # .envファイルを編集して必要な変数を設定
    
    # dotenvxを使用して実行
    dotenvx up  # 環境変数をロード
    dotenvx exec "python3 fetch_openrouter.py"  # 環境変数を使用して実行
    ```

    サポートされている環境変数：
    *   `DISCORD_WEBHOOK_URL`: Discord Webhook URL（config.yamlの設定より優先）
    *   `DISCORD_NOTIFIER_DISABLED`: "true"に設定するとDiscord通知を無効化
    *   `DATABASE_PATH`: データベースパス（オプショナル）
    *   `LOG_LEVEL`: ログレベル（オプショナル）
    *   `API_*`：API設定（オプショナル）

    直接exportでも使用可能：
    ```bash
    export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your/webhook"
    export DISCORD_NOTIFIER_DISABLED="true"
    python3 fetch_openrouter.py
    ```

2.  **設定**:
    ルートディレクトリに `config.yaml` ファイルを作成してください。テンプレートについては `docs/openrouter-tracker_IMPLEMENTATION.md` を参照してください。
    *   **重要な設定**:
        *   `discord.webhook_url`: Discord WebhookのURL。
        *   `discord.enabled`: Discord通知の有効/無効フラグ。
        *   `database.path`: `models.db` へのパス（相対パスも可、自動的に絶対パスに変換されます）。
        *   `logging.file`: `logs/app.log` へのパス（相対パスも可、自動的に絶対パスに変換されます）。
        *   `logging.level`: ログレベル（INFO, WARNING, ERRORなど）。
        *   `logging.max_size_mb`: ログファイルの最大サイズ（MB）。
        *   `logging.backup_count`: 保持するバックアップファイル数。
        *   `api.base_url`: データ取得先のURL。
        *   `api.timeout`: リクエストタイムアウト（秒）。
        *   `api.max_retries`: 最大リトライ回数。
        *   `api.retry_delay`: リトライ間の待機時間（秒）。
        *   `api.user_agent`: HTTPリクエストのUser-Agent。
        *   `llm_parser.enabled`: 将来的なLLMパーサーの有効/無効フラグ。

## プロジェクトの実行

### 手動実行
```bash
python3 fetch_openrouter.py
```

### 自動実行 (Cron)
プロジェクトはCronを使用して1日2回（例: 午前6時と午後6時）実行するように設計されています。
Cronエントリの例:
```bash
0 6 * * * /usr/bin/python3 /path/to/openrouter-tracker/fetch_openrouter.py
```

## 開発規約
*   **仮想環境**: pythonでの開発時は適切に仮想環境を構築してから行うこと( uv venv など)。
*   **言語**: Python 3。
*   **スタイル**: 型ヒント（Type hinting）の使用が推奨されます。標準的なPython PEP 8規約に従ってください。
*   **データベース**: `sqlite3` 標準ライブラリを使用します。リソースが限られた環境でのロックを処理するために、接続管理（コンテキストマネージャを使用）とWALモードを確実に行ってください。
*   **エラー処理**: ネットワークリクエストには堅牢なエラー処理（指数バックオフによる再試行）が必要です。Discord通知にもレート制限対策とリトライロジックを実装してください。
*   **今後の計画**: ソースデータ形式の変更に対応するために、LLMベースのパーサー (`llm_parser.py`) が計画されています。