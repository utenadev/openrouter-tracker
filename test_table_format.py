#!/usr/bin/env python3
"""Table format data fetching test script"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import logging

import yaml

from fetch_openrouter import fetch_markdown
from fetch_openrouter import parse_markdown

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def test_table_format_fetch():
    """実際のAPIからテーブル形式データを取得してパースするテスト"""
    print("Testing table format data fetching from OpenRouter...")

    try:
        # 設定読み込み
        with open("config.yaml") as f:
            config = yaml.safe_load(f)

        # データ取得
        print("Fetching data from OpenRouter API...")
        markdown = fetch_markdown(config, logger)

        # Display part of the data (for debugging)
        print("\n=== Raw Markdown Data (first 500 chars) ===")
        print(markdown[:500])
        print("...")

        # パース
        print("\nParsing table format data...")
        models = parse_markdown(markdown, logger)

        # 結果表示
        print(f"\n✓ Successfully parsed {len(models)} models")
        print("\n=== Top 5 Models ===")
        for i, model in enumerate(
            sorted(models, key=lambda x: x["rank_score"], reverse=True)[:5], 1
        ):
            print(f"{i}. {model['name']}")
            print(f"   ID: {model['id']}")
            print(f"   Provider: {model['provider']}")
            print(f"   Rank Score: {model['rank_score']}")
            print(f"   Context: {model['context_length']}")
            print(f"   Input Price: ${model['prompt_price']}/M")
            print(f"   Output Price: ${model['completion_price']}/M")
            print()

        # 総ランクスコアの計算
        total_score = sum(m["rank_score"] for m in models)
        print(f"\nTotal Rank Score: {total_score / 1000:.2f}B")

        return True

    except Exception as e:
        print(f"\n✗ Error during table format test: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_table_format_fetch()
    sys.exit(0 if success else 1)
