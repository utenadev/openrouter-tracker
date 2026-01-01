#!/usr/bin/env python3
"""パターンマッチングのデバッグスクリプト"""

import re

# パターン定義
MODEL_PATTERN = r'\*   \[(.*?)\]\(https://openrouter\.ai/[^)]+\)\s+(\d+\.?\d*[MB]?) tokens'

# データの読み込み
with open("debug_response.md", "r", encoding="utf-8") as f:
    markdown = f.read()

# パターンマッチングのテスト
model_entries = re.findall(MODEL_PATTERN, markdown)

print(f"Found {len(model_entries)} model entries")
print("\nFirst 5 entries:")
for i, match in enumerate(model_entries[:5]):
    print(f"{i+1}. {match}")

# マッチしない行を探す
lines = markdown.split('\n')
for i, line in enumerate(lines):
    if line.startswith('*   ['):
        if not re.search(MODEL_PATTERN, line):
            print(f"\nLine {i+1} doesn't match pattern:")
            print(line[:200])
            break