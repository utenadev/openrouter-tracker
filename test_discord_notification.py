#!/usr/bin/env python3
"""Discord notification test script"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import logging  # noqa: E402

import yaml  # noqa: E402

from discord_notifier import DiscordNotifier  # noqa: E402
from fetch_openrouter import fetch_markdown  # noqa: E402
from fetch_openrouter import parse_markdown  # noqa: E402

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_discord_notification():
    """Discord notification test (environment variables take precedence)"""
    print("Testing Discord notification with table format data...")

    try:
        # 設定読み込み
        with open("config.yaml") as f:
            config = yaml.safe_load(f)

        # データ取得
        print("Fetching data from OpenRouter API...")
        markdown = fetch_markdown(config, logger)

        # パース
        print("Parsing table format data...")
        models = parse_markdown(markdown, logger)

        if not models:
            print("✗ No models found in data")
            return False

        # 週間トークン数でソート
        models.sort(key=lambda x: x["weekly_tokens"], reverse=True)

        # トップ5モデルを取得
        top_models = models[:5]

        # Previous day's rankings (empty dictionary for testing)
        previous_rankings = {}

        # Discord通知のテスト
        print("\nTesting Discord notifier...")

        # 環境変数が設定されていれば優先的に使用
        notifier = DiscordNotifier(enabled=False)  # テストでは無効化

        # トップ5通知
        print("Sending top5 notification (disabled)...")
        notifier.send_top5_notification(top_models, previous_rankings)

        # New model notification (create new model for testing)
        new_models = [
            {
                "id": "test-new-model",
                "name": "Test New Model",
                "provider": "Test Provider",
                "context_length": 32768,
                "weekly_tokens": 100.0,
                "prompt_price": 0.0001,
                "completion_price": 0.0002,
            }
        ]

        print("Sending new models notification (disabled)...")
        notifier.send_new_models_notification(new_models)

        # サマリー通知
        total_tokens = sum(m["weekly_tokens"] for m in models)
        print("Sending summary notification (disabled)...")
        notifier.send_summary(
            total_models=len(models),
            total_tokens=total_tokens,
            new_models_count=len(new_models),
        )

        print("\n✓ Successfully tested Discord notifications")
        print(f"  - Top5 notification: {len(top_models)} models")
        print(f"  - New models notification: {len(new_models)} models")
        print(
            f"  - Summary: {len(models)} total models, "
            f"{total_tokens / 1000:.2f}B tokens"
        )

        # Display environment variable status
        print("\nEnvironment variable status:")
        webhook_status = "set" if notifier.webhook_url else "not set"
        print(f"  - DISCORD_WEBHOOK_URL: {webhook_status}")
        print(f"  - Notifier enabled: {notifier.enabled}")

        return True

    except Exception as e:
        print(f"\n✗ Error during Discord notification test: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_discord_notification()
    sys.exit(0 if success else 1)
