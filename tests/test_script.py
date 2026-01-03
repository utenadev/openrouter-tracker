import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import yaml

from db import DailyStats
from db import Database
from db import Model
from discord_notifier import DiscordNotifier


def test_database_operations():
    """データベース操作のテスト"""
    print("Testing database operations...")

    db_path = Path("test_models.db")
    if db_path.exists():
        db_path.unlink()

    # データベース初期化
    with Database(str(db_path)) as db:
        db.init_db()
        print("✓ Database initialized")

        # テストデータの作成
        test_models = [
            Model(
                id="mistralai/Mistral-7B-Instruct-v0.1",
                name="Mistral 7B",
                provider="Mistral AI",
                context_length=32768,
                description="High-performance 7B model",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            ),
            Model(
                id="meta-llama/Llama-2-7b-chat",
                name="Llama 2 7B",
                provider="Meta",
                context_length=4096,
                description="Llama 2 chat model",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            ),
        ]

        # モデルの保存
        for model in test_models:
            db.upsert_model(model)
        print("✓ Models saved")

        # 日次統計の保存
        today = datetime.now().strftime("%Y-%m-%d")
        daily_stats = [
            DailyStats(
                model_id="mistralai/Mistral-7B-Instruct-v0.1",
                date=today,
                rank=1,
                rank_score=1200.0,
                prompt_price=0.0,
                completion_price=0.0,
            ),
            DailyStats(
                model_id="meta-llama/Llama-2-7b-chat",
                date=today,
                rank=2,
                rank_score=950.0,
                prompt_price=0.0,
                completion_price=0.0,
            ),
        ]
        db.save_daily_stats(daily_stats)
        print("✓ Daily stats saved")

        # データの取得
        models = db.get_all_models()
        print(f"✓ Retrieved {len(models)} models")

        # ランキングの取得
        top_models = db.get_top_models(today, limit=5)
        print(f"✓ Retrieved {len(top_models)} top models")

        # 新規モデル検出
        current_ids = [
            "mistralai/Mistral-7B-Instruct-v0.1",
            "meta-llama/Llama-2-7b-chat",
            "new-model",
        ]
        new_models = db.detect_new_models(current_ids)
        print(f"✓ Detected {len(new_models)} new models")

    # Cleanup
    if db_path.exists():
        db_path.unlink()


def test_discord_notifier():
    """Discord通知のテスト"""
    print("Testing Discord notification...")

    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/test", enabled=False
    )

    # テストデータ
    top_models = [
        {
            "id": "mistralai/Mistral-7B-Instruct-v0.1",
            "name": "Mistral 7B",
            "rank_score": 1200.0,
            "rank": 1,
            "context_length": 32768,
        }
    ]
    previous_rankings = {"mistralai/Mistral-7B-Instruct-v0.1": 2}

    # 通知送信（モックされないがenabled=Falseなので何もしない）
    notifier.send_top5_notification(top_models, previous_rankings)
    print("✓ Notification test completed")


def test_config_loading():
    """設定読み込みのテスト"""
    print("Testing config loading...")
    config_path = Path("config.yaml")

    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
            assert "database" in config
            assert "discord" in config
            assert "api" in config
            print("✓ Config loaded and verified")
    else:
        print("! config.yaml not found, skipping test")


if __name__ == "__main__":
    test_database_operations()
    test_discord_notifier()
    test_config_loading()
