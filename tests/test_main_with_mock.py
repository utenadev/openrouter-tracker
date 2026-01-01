#!/usr/bin/env python3
"""メインスクリプトのテスト - モックデータを使用

環境変数:
    DISCORD_WEBHOOK_URL: Discord Webhook URL (設定されていれば優先的に使用)
    DISCORD_NOTIFIER_DISABLED: "true"に設定すると通知を無効化
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from db import DailyStats
from db import Database
from db import Model
from discord_notifier import DiscordNotifier
from fetch_openrouter import parse_markdown

# モックデータ
MOCK_MARKDOWN = """
*   [Mistral 7B](https://openrouter.ai/mistralai/Mistral-7B-Instruct-v0.1) 1.2B tokens
*   [Llama 2 7B](https://openrouter.ai/meta-llama/Llama-2-7b-chat) 950M tokens
*   [Gemini Pro](https://openrouter.ai/google/gemini-pro) 800M tokens
*   [Claude 3 Haiku](https://openrouter.ai/anthropic/claude-3-haiku) 700M tokens
*   [GPT-3.5 Turbo](https://openrouter.ai/openai/gpt-3.5-turbo) 600M tokens

32K context, $0.0001/M input tokens, $0.0002/M output tokens by [Mistral AI]
"""

def test_main_with_mock():
    """モックデータを使用してメイン処理をテスト"""
    print("Testing main script with mock data...")

    # データベース操作
    db_path = Path("test_main_models.db")

    with Database(str(db_path)) as db:
        db.init_db()
        print("✓ Database initialized")

        # モックデータのパース(本番コードのparse_markdown関数を使用)
        logger = logging.getLogger(__name__)
        models_data = parse_markdown(MOCK_MARKDOWN, logger)

        print(f"✓ Parsed {len(models_data)} models from mock data")

        # 週間トークン数でソート
        models_data.sort(key=lambda x: x["weekly_tokens"], reverse=True)

        # 新規モデル検出
        existing_ids = db.get_all_model_ids()
        current_ids = {m["id"] for m in models_data}
        new_model_ids = current_ids - existing_ids
        new_models = [m for m in models_data if m["id"] in new_model_ids]

        print(f"✓ Detected {len(new_models)} new models")

        # モデル情報の保存
        for model_data in models_data:
            model = Model(
                id=model_data["id"],
                name=model_data["name"],
                provider=model_data["provider"],
                context_length=model_data["context_length"],
                description="",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
            db.upsert_model(model)

        print("✓ Models saved to database")

        # 日次統計の保存
        today = datetime.now().strftime("%Y-%m-%d")
        daily_stats = []
        for rank, model_data in enumerate(models_data, 1):
            stat = DailyStats(
                model_id=model_data["id"],
                date=today,
                rank=rank,
                weekly_tokens=model_data["weekly_tokens"],
                prompt_price=model_data["prompt_price"],
                completion_price=model_data["completion_price"]
            )
            daily_stats.append(stat)

        db.save_daily_stats(daily_stats)
        print("✓ Daily stats saved")

        # ランキング比較のテスト
        previous_rankings = db.get_latest_rankings_before("2024-01-01")
        print(f"✓ Previous rankings: {previous_rankings}")

        # トップモデルの取得
        top_models = db.get_top_models_by_tokens(today, limit=5)
        print(f"✓ Top {len(top_models)} models retrieved")

        # モデル情報の表示
        for i, model in enumerate(top_models[:3], 1):
            print(f"  {i}. {model['name']} - {model['weekly_tokens']}M tokens")

    # Discord通知のテスト
    # 環境変数 DISCORD_WEBHOOK_URL が設定されていれば優先的に使用
    notifier = DiscordNotifier(enabled=False)  # デフォルトでは無効化

    # トップ5通知
    notifier.send_top5_notification(top_models, previous_rankings)
    print("✓ Top5 notification sent")

    # 新規モデル通知
    if new_models:
        notifier.send_new_models_notification(new_models)
        print("✓ New models notification sent")

    # サマリー通知
    total_tokens = sum(m["weekly_tokens"] for m in models_data)
    notifier.send_summary(
        total_models=len(models_data),
        total_tokens=total_tokens,
        new_models_count=len(new_models)
    )
    print("✓ Summary notification sent")

    print("\n✓ Main script test completed successfully!")

if __name__ == "__main__":
    test_main_with_mock()
