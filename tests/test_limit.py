#!/usr/bin/env python3
"""limitパラメータのテストスクリプト"""

import requests
import yaml

# 設定ファイルの読み込み
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# ヘッダーの設定
headers = {"User-Agent": config["api"]["user_agent"]}

# 複数のlimit値でテスト
limit_values = [10, 20, 30, 50, 100]

for limit in limit_values:
    print(f"\nTesting with limit={limit}")

    # URLの作成
    url = f"https://openrouter.ai/models?max_price=0&order=top-weekly&limit={limit}"

    try:
        response = requests.get(url, timeout=config["api"]["timeout"], headers=headers)
        response.raise_for_status()

        # モデル数のカウント
        import re

        MODEL_PATTERN = (
            r"\*   \[(.*?)\]\(https://openrouter\.ai/[^)]+\)\s+(\d+\.?\d*[MB]?) tokens"
        )
        model_entries = re.findall(MODEL_PATTERN, response.text)

        print(f"  ✓ Success: {len(model_entries)} models found")

        # 最初の3モデルを表示
        if model_entries:
            print("  First 3 models:")
            for i, (name, tokens) in enumerate(model_entries[:3], 1):
                print(f"    {i}. {name} - {tokens}")

    except Exception as e:
        print(f"  ✗ Failed: {e}")
