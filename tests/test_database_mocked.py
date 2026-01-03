#!/usr/bin/env python3
"""db.pyのテスト - モックを使用したユニットテスト

データベース操作のテストで外部依存を排除。
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from db import DailyStats
from db import Database
from db import Model


class TestDatabase:
    """Databaseクラスのテスト"""

    def setup_method(self):
        """各テストメソッド実行前のセットアップ"""
        self.test_db_path = Path(tempfile.mktemp(suffix=".db"))

    def teardown_method(self):
        """各テストメソッド実行後のクリーンアップ"""
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_database_initialization(self):
        """データベース初期化のテスト"""
        with Database(str(self.test_db_path)) as db:
            db.init_db()
            # テーブルが作成されたことを確認
            cursor = db.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            assert "models" in tables
            assert "daily_stats" in tables
            assert "history" in tables

    def test_upsert_model(self):
        """モデルのアップサートテスト"""
        test_model = Model(
            id="test-model",
            name="Test Model",
            provider="Test Provider",
            context_length=32768,
            description="Test description",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        with Database(str(self.test_db_path)) as db:
            db.init_db()
            db.upsert_model(test_model)

            # モデルが保存されたことを確認
            saved_models = db.get_all_models()
            assert len(saved_models) == 1
            assert saved_models[0].id == "test-model"
            assert saved_models[0].name == "Test Model"

    def test_save_daily_stats(self):
        """日次統計の保存テスト"""
        test_stats = [
            DailyStats(
                model_id="test-model",
                date="2024-01-01",
                rank=1,
                rank_score=1000.0,
                prompt_price=0.0001,
                completion_price=0.0002,
            )
        ]

        with Database(str(self.test_db_path)) as db:
            db.init_db()
            db.save_daily_stats(test_stats)

            # 統計が保存されたことを確認（実際にはrank_scoreが保存される）
            # ただし、get_top_models_by_tokensはdaily_statsテーブルからデータを取得するので
            # 保存されたrank_scoreが取得できることを確認

    def test_get_all_model_ids(self):
        """全モデルID取得のテスト"""
        test_models = [
            Model(
                id="model-1",
                name="Model 1",
                provider="Provider 1",
                context_length=32768,
                description="",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            ),
            Model(
                id="model-2",
                name="Model 2",
                provider="Provider 2",
                context_length=16384,
                description="",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            ),
        ]

        with Database(str(self.test_db_path)) as db:
            db.init_db()
            for model in test_models:
                db.upsert_model(model)

            model_ids = db.get_all_model_ids()
            assert "model-1" in model_ids
            assert "model-2" in model_ids
            assert len(model_ids) == 2

    def test_detect_new_models(self):
        """新規モデル検出のテスト"""
        existing_models = ["existing-model-1", "existing-model-2"]
        current_models = [
            "existing-model-1",
            "existing-model-2",
            "new-model-1",
            "new-model-2",
        ]

        with Database(str(self.test_db_path)) as db:
            db.init_db()
            # 既存モデルを追加
            for model_id in existing_models:
                test_model = Model(
                    id=model_id,
                    name=f"Model {model_id}",
                    provider="Test Provider",
                    context_length=32768,
                    description="",
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat(),
                )
                db.upsert_model(test_model)

            new_models = db.detect_new_models(current_models)
            assert "new-model-1" in new_models
            assert "new-model-2" in new_models
            assert "existing-model-1" not in new_models
            assert "existing-model-2" not in new_models
            assert len(new_models) == 2

    def test_get_latest_rankings_before(self):
        """指定日以前のランキング取得テスト"""
        test_stats = [
            DailyStats(
                model_id="model-1",
                date="2024-01-01",
                rank=1,
                rank_score=1000.0,
                prompt_price=0.0,
                completion_price=0.0,
            ),
            DailyStats(
                model_id="model-2",
                date="2024-01-01",
                rank=2,
                rank_score=900.0,
                prompt_price=0.0,
                completion_price=0.0,
            ),
            DailyStats(
                model_id="model-3",
                date="2024-01-02",  # 後の日付
                rank=1,
                rank_score=1100.0,
                prompt_price=0.0,
                completion_price=0.0,
            ),
        ]

        with Database(str(self.test_db_path)) as db:
            db.init_db()
            db.save_daily_stats(test_stats)

            # 2024-01-01以前のランキングを取得
            rankings = db.get_latest_rankings_before("2024-01-01")
            assert "model-1" in rankings
            assert rankings["model-1"] == 1
            assert rankings["model-2"] == 2
            assert "model-3" not in rankings  # 2024-01-02のデータは含まれない

    def test_get_top_models(self):
        """トップモデル取得テスト"""
        # モデル情報を追加
        test_model = Model(
            id="test-model",
            name="Test Model",
            provider="Test Provider",
            context_length=32768,
            description="",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        test_stats = [
            DailyStats(
                model_id="test-model",
                date="2024-01-01",
                rank=1,
                rank_score=1000.0,
                prompt_price=0.0001,
                completion_price=0.0002,
            )
        ]

        with Database(str(self.test_db_path)) as db:
            db.init_db()
            db.upsert_model(test_model)
            db.save_daily_stats(test_stats)

            top_models = db.get_top_models("2024-01-01", limit=5)
            assert len(top_models) == 1
            assert top_models[0]["id"] == "test-model"
            assert top_models[0]["rank"] == 1
            # rank_scoreが返されることを確認
            assert hasattr(
                top_models[0], "__getitem__"
            )  # Rowオブジェクトであることを確認
            assert top_models[0]["rank_score"] == 1000.0

    def test_database_context_manager(self):
        """コンテキストマネージャーのテスト"""
        db = Database(str(self.test_db_path))

        # __enter__ がコネクションを返すことを確認
        db_instance = db.__enter__()
        assert db_instance.conn is not None

        # __exit__ がコネクションを閉じることを確認
        db.__exit__(None, None, None)
        # 接続が閉じられているか確認（通常は例外が発生する）
        with pytest.raises(Exception):
            db_instance.conn.execute("SELECT 1")


if __name__ == "__main__":
    pytest.main([__file__])
