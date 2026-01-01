#!/usr/bin/env python3
"""データベースからデータを取得して確認"""

from db import Database
from datetime import datetime

db_path = "models.db"

with Database(db_path) as db:
    # モデルの取得
    models = db.get_all_models()
    print(f"Total models in database: {len(models)}")
    
    # トップモデルの取得
    today = datetime.now().strftime('%Y-%m-%d')
    top_models = db.get_top_models_by_tokens(today, limit=5)
    
    print(f"\nTop 5 models for {today}:")
    for i, model in enumerate(top_models, 1):
        print(f"{i}. {model['name']}")
        print(f"   Provider: {model['provider']}")
        print(f"   Weekly tokens: {model['weekly_tokens']}M")
        print(f"   Context length: {model['context_length']}")
        print(f"   Rank: {model['rank']}")
        print()