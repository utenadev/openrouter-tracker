# OpenRouter Tracker コンテキスト

## プロジェクト概要
**OpenRouter Tracker** は、OpenRouterの無料モデルの使用統計とランキングを追跡するために設計されたPythonベースのユーティリティです。OpenRouterから（`r.jina.ai`経由で）データを取得し、ローカルのSQLiteデータベースに保存して、日次レポートをDiscordチャンネルに送信します。

## 主な機能
*   **データ取得**: 週間トークン使用量、コンテキスト長、価格などのモデルデータをスクレイピングします。
*   **データベース**: モデル情報と日次統計をSQLite (`models.db`) に保存します。
*   **通知**: 以下のDiscord通知を送信します：
    *   週間トークン使用量によるトップ5モデル。
    *   新規モデルの追加。
    *   日次サマリー。
*   **ロギング**: ローテーションサポート付きの詳細なロギング。

## アーキテクチャと主要ファイル
*   `fetch_openrouter.py`: メインのエントリーポイント。取得、解析、データベース更新、通知を統括します。
*   `db.py`: すべてのSQLiteデータベース操作（スキーマ作成、Upsert、クエリ）を処理します。
*   `discord_notifier.py`: Discord Webhookの統合とメッセージフォーマットを管理します。
*   `config.yaml`: APIエンドポイント、データベースパス、ロギング、Discord認証情報の設定ファイルです。
*   `models.db`: SQLiteデータベースファイル（実行時に作成されます）。
*   `docs/`: 詳細な実装メモと仕様が含まれています。

## セットアップと設定

1.  **依存関係**:
    ```bash
    pip install -r requirements.txt
    ```
    必要なパッケージ: `pyyaml`, `requests`。

2.  **設定**:
    ルートディレクトリに `config.yaml` ファイルを作成してください。テンプレートについては `docs/openrouter-tracker_IMPLEMENTATION.md` を参照してください。
    *   **重要な設定**:
        *   `discord.webhook_url`: Discord WebhookのURL。
        *   `database.path`: `models.db` へのパス（相対パスも可、自動的に絶対パスに変換されます）。
        *   `logging.file`: `logs/app.log` へのパス（相対パスも可、自動的に絶対パスに変換されます）。

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