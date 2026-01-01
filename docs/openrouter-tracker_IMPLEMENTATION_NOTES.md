# openrouter-tracker 実装メモ (v2)

## 概要

このドキュメントは、システム実装時の注意点、テスト方法、および運用上のベストプラクティスをまとめたものです。実装ドキュメント (v2) の内容に基づいています。

---

## 重要な実装ポイント

### 1. パス処理の堅牢化

**注意点**: スクリプトがどこから実行されても（Cronなど）正しく設定やDBを見つけられる必要があります。

**推奨実装**:
```python
# fetch_openrouter.py
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()

def load_config(config_path="config.yaml"):
    # config.yaml 自体も絶対パスで探す
    abs_config_path = BASE_DIR / config_path
    # ... 読み込み ...
    # config内のパスが相対なら絶対パスに変換
    if not Path(config['database']['path']).is_absolute():
        config['database']['path'] = str(BASE_DIR / config['database']['path'])
```

**実装状況**: ✅ 実装済み
- `BASE_DIR`定数を追加
- `load_config`関数で絶対パスを使用

---

### 2. ランキング比較のロジック (24時間ルール)

**注意点**: 単純に「1日前 (yesterday)」を検索すると、前日の実行が失敗していた場合に比較対象がなくなります。

**解決策**: 「24時間以上前のデータの中で、最も新しいもの」を取得します。
```python
# db.py
def get_latest_rankings_before(self, date_threshold: str) -> Dict[str, int]:
    """
    date_threshold (例: 1日前の日付) 以前のデータで、
    DBに存在する最新のランキングを取得する
    """
    query = """
        SELECT model_id, rank FROM daily_stats 
        WHERE date = (SELECT MAX(date) FROM daily_stats WHERE date <= ?)
    """
    # ... 実行 ...
```

---

### 3. 新規モデル検出のタイミング

**注意点**: データを保存 (Upsert) した後に検出すると、すべて「既存」になってしまいます。

**正しいフロー**:
1. データをフェッチする
2. **DB内の既存ID一覧を取得する**
3. フェッチしたデータと既存IDを比較し、差分を「新規モデル」として特定する
4. データをDBに保存 (Upsert) する
5. 通知を送信する

---

### 4. SQLiteの同時実行制御 (WALモード)

**注意点**: Raspberry Pi等のリソース制限環境で、読み書きが衝突して `database is locked` が発生するのを防ぎます。

**推奨設定**:
```python
def __enter__(self):
    self.conn = sqlite3.connect(self.db_path, timeout=30.0)
    self.conn.execute("PRAGMA journal_mode=WAL") # 書き込み中も読み込みをブロックしない
    self.conn.row_factory = sqlite3.Row
    return self
```

**実装状況**: ✅ 実装済み

---

### 5. 仮想環境と実行パス

**注意点**: `python` コマンドがシステム側を指していると、依存ライブラリ不足で落ちます。

**推奨**: Cronやシェルスクリプトでは仮想環境内の python バイナリをフルパスで指定します。
```bash
# Cronでの例
0 6 * * * /home/user/openrouter-tracker/venv/bin/python3 /home/user/openrouter-tracker/fetch_openrouter.py
```

---

## テストとデバッグ

### 1. 疑似データの作成

ランキング変動をテストする場合、SQLiteを直接操作して過去の日付のデータを作成します。
```sql
INSERT INTO daily_stats (model_id, date, rank, weekly_tokens) 
VALUES ('test-model', '2026-01-01', 1, 1000.0);
```

### 2. パースエラーのデバッグ

r.jina.ai の出力が変わった場合に備え、生のMarkdownを保存するデバッグモードがあると便利です。
```python
if logger.isEnabledFor(logging.DEBUG):
    with open("debug_response.md", "w") as f:
        f.write(markdown_content)
```

---

## 運用・セキュリティ

### 1. .gitignore の自動化

セットアップ時に以下のファイルを必ず除外するようにします：
- `config.yaml`（機密情報を含む）
- `*.db`（バイナリデータ）
- `venv/`
- `logs/`

### 2. Webhookのレート制限

Discord Webhookは短時間に送りすぎると制限がかかります。
- `Top 5`, `新規モデル`, `サマリー` をできるだけ一つの埋め込みメッセージ（Embed）にまとめるか、送信間に `time.sleep(1)` を入れることを検討してください。

**実装状況**: ✅ 実装済み
- レート制限対策として`time.sleep(1)`を追加
- リトライロジックを追加

---

## トラブルシューティング

| 症状 | 原因 | 対策 |
|------|------|------|
| ランキング変動が常に 0 | 比較対象の古いデータがない | 24時間以上前のデータがDBにあるか確認 |
| `ImportError` | 仮想環境が未適用 | `venv/bin/python3` を使用しているか確認 |
| `locked` エラー | 重複起動 | WALモードの確認と、PIDファイルによる二重起動防止を検討 |
| Discord通知失敗 | レート制限またはネットワークエラー | リトライロジックの確認と、レート制限対策の実施 |

---

以上が修正・強化された実装メモです。
