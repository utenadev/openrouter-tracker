#!/usr/bin/env python3
"""実際のデータを取得して確認するためのデバッグスクリプト"""

import requests
import yaml

# 設定ファイルの読み込み
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# ヘッダーの設定
headers = {
    "User-Agent": config["api"]["user_agent"]
}

# データの取得
try:
    response = requests.get(
        config["api"]["base_url"],
        timeout=config["api"]["timeout"],
        headers=headers
    )
    response.raise_for_status()

    # データをファイルに保存
    with open("debug_response.md", "w", encoding="utf-8") as f:
        f.write(response.text)

    print("✓ Data fetched successfully")
    print(f"Response length: {len(response.text)} characters")
    print("\nFirst 500 characters:")
    print(response.text[:500])

except Exception as e:
    print(f"✗ Failed to fetch data: {e}")
