# OpenRouter Tracker 厳しめコードレビュー

レビュー日時: 2026-01-02
レビューアー: opencode + glm47

---

## 1. CI/CD設定の重大な誤り (Critical)

### 問題点

**`.github/workflows/ci.yml:36`**, **`.github/workflows/pr.yml:34`**
```yaml
run: pytest -v --cov=llminfo_cli --cov-report=term-missing
```

プロジェクト名が`openrouter-tracker`なのに`llminfo_cli`を参照している。テストは一切実行されず成功する。

**`.github/workflows/ci.yml:26`**, **`.github/workflows/pr.yml:24`**
```yaml
key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
```

`pyproject.toml`が存在しないのにキャッシュキーに使用している。キャッシュが常にmissになる。

**`.github/workflows/ci.yml:39-41`**
```bash
coverage=$(python -m coverage report --format=coverage-lcov | grep -o '^[^]' | awk '{ if ($4 >= 80) print "✅ PASS"; else print "❌ FAIL"; exit($4 >= 80 ? 0 : 1) }')
```

コマンドが正しく動作しない。`grep -o '^[^]'`で空文字のみマッチ、`$4`列が存在しない。カバレッジチェックは実質機能していない。

**`.github/workflows/ci.yml:50`**, **`.github/workflows/pr.yml:43`**
```yaml
run: mypy llminfo_cli tests
```

`llminfo_cli`ではなく`fetch_openrouter.py`などを指定すべき。

### 推奨修正

```yaml
# 正しいパッケージ名に修正
run: pytest -v --cov=. --cov-report=term-missing

# pyproject.tomlの代わりにrequirements.txtを使用
key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}

# カバレッジチェックを修正
- name: Check coverage
  run: |
    coverage report --fail-under=80

# 正しいモジュール名に修正
run: mypy fetch_openrouter.py discord_notifier.py db.py tests/
```

---

## 2. Pythonバージョンの不一致

### 問題点

**`.github/workflows/ci.yml:20`**, **`.github/workflows/pr.yml:18`**
```yaml
python-version: "3.14"
```

**`ruff.toml:5`**
```toml
target-version = "py38"
```

CIではPython 3.14だが、ruffはPython 3.8をターゲットにしている。READMEには「Python 3.8+」とあるが、実際にはPython 3.14で動かさないとCIが通らない。

### 推奨修正

どちらかに統一する（推奨: Python 3.11）：
- CI: `python-version: "3.11"`
- ruff: `target-version = "py311"`
- README: `Python 3.11+`

---

## 3. Gitignoreに含まれるべきファイルがリポジトリにある

### 問題点

**`.gitignore:68-70`**
```gitignore
*.db
*.sqlite
*.sqlite3
```

`models.db-shm`と`models.db-wal`がリポジトリ内に存在する。WALモード用の一時ファイルなのでコミットすべきでない。

### 推奨修正

```bash
# 除外
rm models.db-shm models.db-wal

# .gitignoreに追加
*.db-shm
*.db-wal
```

---

## 4. setup.shのパスハードコーディング

### 問題点

**`setup.sh:7-10`**
```bash
mkdir -p ~/openrouter-tracker/logs

cd ~/openrouter-tracker
```

ユーザーが`~/openrouter-tracker`以外の場所にcloneした場合、動かない。スクリプトを実行したディレクトリを基準にすべき。

### 推奨修正

```bash
#!/bin/bash
set -e

# スクリプトのディレクトリを使用
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ディレクトリ作成
mkdir -p logs
```

---

## 5. テストファイルの問題

### 問題点

**`tests/test_script.py:29`**
```python
db_path = Path("test_models.db")
```

テスト実行後に`test_models.db`が残る。`@pytest.fixture`を使って前後処理を行うべき。

また、テストファイルの命名規則が不統一：
- `test_script.py` → OK
- `test_main_with_mock.py` → OK
- `check_database.py` → NG（`test_`プレフィックスなし）
- `fetch_openrouter_json.py` → NG（テスト名前空間外）

### 推奨修正

```python
import pytest

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    yield str(db_path)
    # テスト後のクリーンアップはpytestが自動で行う

def test_database_operations(temp_db):
    with Database(temp_db) as db:
        # テストコード
        pass
```

---

## 6. DiscordNotifierの例外処理

### 問題点

**`discord_notifier.py:152-160`**
```python
except Exception as e:
    logger.error("Failed to send Discord notification: %s", e)
    # リトライロジックを追加
    time.sleep(2)
    try:
        response = requests.post(self.webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Discord notification sent successfully on retry")
    except Exception as e:
        logger.error("Failed to send Discord notification on retry: %s", e)
```

リトライ失敗時、例外を飲み込んでいる。通知失敗を検知できない。失敗時に再raiseすべき。

### 推奨修正

```python
except Exception as e:
    logger.error("Failed to send Discord notification: %s", e)
    if self.webhook_url:
        time.sleep(2)
        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Discord notification sent successfully on retry")
        except Exception as retry_error:
            logger.error("Failed to send Discord notification on retry: %s", retry_error)
            raise  # 例外を再スロー
```

---

## 7. Databaseの競合処理不足

### 問題点

**`db.py:33-36`**
```python
def __enter__(self):
    self.conn = sqlite3.connect(self.db_path, timeout=30.0)
    self.conn.execute("PRAGMA journal_mode=WAL")
    self.conn.row_factory = sqlite3.Row
    return self
```

WALモードは設定されているが、複数プロセスからの同時アクセス時のエラーハンドリングがない。`database is locked`エラーが発生した場合のリトライロジックがない。

### 推奨修正

```python
def __enter__(self):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            self.conn = sqlite3.connect(self.db_path, timeout=30.0)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.row_factory = sqlite3.Row
            return self
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
                continue
            raise
```

---

## 8. パース処理の脆弱性

### 問題点

**`fetch_openrouter.py:249-251`**
```python
# 周間トークン数はAPIから取得できないため、デフォルト値を設定
# 実際の実装では、別の方法で取得する必要があります
weekly_tokens = 0.0  # デフォルト値
```

週間トークン数が常に0になり、ランキングが機能していない。READMEには「Top 5 models by weekly token usage」とあるが実装されていない。

### 推奨修正

以下のいずれかを検討：
1. 別のAPIエンドポイントから週間トークン数を取得
2. テーブル形式のMarkdownに週間トークン列が含まれるように変更
3. 週間トークンを追跡できない旨をREADMEに明記し、別のメトリクス（価格など）でランキング

---

## 9. セキュリティ上の懸念

### 問題点

**`requirements.txt`**
```
pyyaml>=6.0
requests>=2.31.0
```

バージョン範囲が広すぎる。セキュリティアップデートが入っても自動でインストールされるため、バージョンを固定すべき。

**`fetch_openrouter.py:31-32`**
```python
headers = {
    "User-Agent": config["api"]["user_agent"]
}
```

config.yamlにUser-Agentがハードコードされているが、APIの仕様変更やブロックのリスクがある。

### 推奨修正

```txt
pyyaml~=6.0
requests~=2.31.0
```

または、依存管理ツール（poetryやpip-tools）の導入を検討。

---

## 10. 型ヒントの不備

### 問題点

**`fetch_openrouter.py:272-385`** - `main()`関数に戻り値がないが、スクリプトとして扱われている。

**`discord_notifier.py:26`**
```python
def send_top5_notification(
    self, models: List[Dict], previous_rankings: Dict[str, int]
):
```

`List[Dict]`の中身の型定義が不十分。`TypedDict`やdataclassを使うべき。

### 推奨修正

```python
from typing import TypedDict

class ModelRanking(TypedDict):
    id: str
    name: str
    weekly_tokens: float
    context_length: int
    rank: int

def send_top5_notification(
    self,
    models: List[ModelRanking],
    previous_rankings: Dict[str, int]
):
    ...
```

---

## 11. ドキュメントファイルの整理

### 問題点

ルートディレクトリに以下のドキュメントファイルが散らばっている：
- `main_response.md`
- `debug_response.md`
- `GEMINI.md`
- `HYBRID_DATA_FETCHING_DESIGN.md`

これらは`docs/`以下に移動すべき。

### 推奨修正

```bash
mv main_response.md docs/
mv debug_response.md docs/
mv GEMINI.md docs/
mv HYBRID_DATA_FETCHING_DESIGN.md docs/
```

---

## 12. テストカバレッジの欠如

### 問題点

テストが単純な動作確認でしかなく、以下の重要なパスがテストされていない：
- APIリクエスト失敗時の挙動
- パースエラー時の挙動
- データベースエラー時の挙動
- 環境変数オーバーライドの動作

### 推奨修正

統合テストの追加：
```python
@pytest.mark.integration
def test_api_failure_handling():
    with pytest.raises(RuntimeError):
        # モックでAPIエラーを発生させる
        ...

@pytest.mark.integration
def test_parse_error_handling():
    invalid_markdown = "Invalid markdown"
    with pytest.raises(ValueError):
        parse_markdown(invalid_markdown, logger)
```

---

## 総評

**動作はするが、本番環境運用には適さないレベル**。特にCI/CD設定が壊れているため、PRマージ時に品質担保ができていない。

### 最優先で修正すべき項目

1. **CI/CD設定の修正** - これが最も重要。品質チェックが機能していない
2. **週間トークン数の実装** - READMEの機能説明と実装が一致していない
3. **テストの充実化** - エラーケースのテストが不足
4. **例外処理の改善** - 通知失敗等を検知できない
5. **ファイル整理** - 不要な一時ファイルがリポジトリにある

### 優先度別タスクリスト

| 優先度 | タスク | 影響 |
|--------|------|------|
| P0 | CI/CD設定修正 | 品質担保なし |
| P0 | 週間トークン数実装 | 機能不全 |
| P1 | 例外処理改善 | 運用時の問題検知不可 |
| P1 | テスト追加 | 回帰テスト不可 |
| P2 | ファイル整理 | リポジトリ汚染 |
| P2 | 型ヒント改善 | メンテナビリティ低下 |
| P3 | ドキュメント移動 | リポジトリ整理 |
| P3 | セキュリティ改善 | 低リスクだが改善推奨 |
