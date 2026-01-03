import sqlite3
import time
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
            cursor = self.conn.execute(
                """
                INSERT INTO models (id, name, provider, context_length, description)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    provider = excluded.provider,
                    context_length = excluded.context_length,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    model.id,
                    model.name,
                    model.provider,
                    model.context_length,
                    model.description,
                ),
            )

            # 新規追加の場合、履歴に記録
            if cursor.rowcount > 0 and cursor.lastrowid > 0:
                is_new = (
                    self.conn.execute(
                        "SELECT COUNT(*) FROM history "
                        "WHERE model_id = ? AND event = 'new'",
                        (model.id,),
                    ).fetchone()[0]
                    == 0
                )

                if is_new:
                    self.conn.execute(
                        """
                        INSERT INTO history (model_id, event, details)
                        VALUES (?, 'new', ?)
                    """,
                        (model.id, f"New model added: {model.name}"),
                    )

    def save_daily_stats(self, stats: list[DailyStats]):
        """日次統計を保存"""
        with self.conn:
            for stat in stats:
                self.conn.execute(
                    """
                    INSERT OR REPLACE INTO daily_stats
                    (model_id, date, rank, weekly_tokens,
                     prompt_price, completion_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stat.model_id,
                        stat.date,
                        stat.rank,
                        stat.weekly_tokens,
                        stat.prompt_price,
                        stat.completion_price,
                    ),
                )

    def get_latest_rankings_before(self, date_threshold: str) -> dict[str, int]:
        """指定日以前の直近のランキングを取得(24時間以上前の比較用)"""
        # 指定日以前で最も新しい日付を取得
        latest_date_row = self.conn.execute(
            """
            SELECT MAX(date) as max_date
            FROM daily_stats
            WHERE date <= ?
        """,
            (date_threshold,),
        ).fetchone()

        if not latest_date_row or not latest_date_row["max_date"]:
            return {}

        target_date = latest_date_row["max_date"]

        previous_rankings = self.conn.execute(
            """
            SELECT model_id, rank
            FROM daily_stats
            WHERE date = ?
        """,
            (target_date,),
        ).fetchall()

        return {row["model_id"]: row["rank"] for row in previous_rankings}

    def get_top_models_by_tokens(self, date: str, limit: int = 5) -> list[dict]:
        """指定日のトークン数トップNモデルを取得"""
        return self.conn.execute(
            """
            SELECT m.*, d.rank, d.weekly_tokens
            FROM daily_stats d
            JOIN models m ON d.model_id = m.id
            WHERE d.date = ?
            ORDER BY d.rank
            LIMIT ?
        """,
            (date, limit),
        ).fetchall()

    def get_all_models(self) -> list[Model]:
        """全モデルを取得"""
        rows = self.conn.execute("SELECT * FROM models").fetchall()
        return [Model(**dict(row)) for row in rows]

    def get_all_model_ids(self) -> set[str]:
        """全モデルIDのセットを取得"""
        rows = self.conn.execute("SELECT id FROM models").fetchall()
        return {row["id"] for row in rows}

    def detect_new_models(self, current_models: list[str]) -> list[str]:
        """新規モデルを検出"""
        existing_models = self.get_all_model_ids()
        new_models = [
            model_id for model_id in current_models if model_id not in existing_models
        ]
        return new_models
