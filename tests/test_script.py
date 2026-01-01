#!/usr/bin/env python3
"""テストスクリプト - モックデータを使用して動作を確認"""

import sys
import os
from pathlib import Path
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from db import Database, Model, DailyStats
from discord_notifier import DiscordNotifier

def test_database_operations():
    """データベース操作のテスト"""
    print("Testing database operations...")
    
    db_path = Path("test_models.db")
    
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
                updated_at=datetime.now().isoformat()
            ),
            Model(
                id="meta-llama/Llama-2-7b-chat",
                name="Llama 2 7B",
                provider="Meta",
                context_length=4096,
                description="Llama 2 chat model",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat()
            )
        ]
        
        # モデルの保存
        for model in test_models:
            db.upsert_model(model)
        print("✓ Models saved")
        
        # 日次統計の保存
        today = datetime.now().strftime('%Y-%m-%d')
        daily_stats = [
            DailyStats(
                model_id="mistralai/Mistral-7B-Instruct-v0.1",
                date=today,
                rank=1,
                weekly_tokens=1200.0,
                prompt_price=0.0,
                completion_price=0.0
            ),
            DailyStats(
                model_id="meta-llama/Llama-2-7b-chat",
                date=today,
                rank=2,
                weekly_tokens=950.0,
                prompt_price=0.0,
                completion_price=0.0
            )
        ]
        
        db.save_daily_stats(daily_stats)
        print("✓ Daily stats saved")
        
        # データの取得
        models = db.get_all_models()
        print(f"✓ Retrieved {len(models)} models")
        
        top_models = db.get_top_models_by_tokens(today, limit=5)
        print(f"✓ Retrieved {len(top_models)} top models")
        
        # 新規モデル検出
        current_ids = ["mistralai/Mistral-7B-Instruct-v0.1", "meta-llama/Llama-2-7b-chat", "new-model"]
        new_models = db.detect_new_models(current_ids)
        print(f"✓ Detected {len(new_models)} new models: {new_models}")

def test_discord_notifier():
    """Discord通知のテスト（実際には送信しない）"""
    print("\nTesting Discord notifier...")
    
    # テスト用のモックWebhook URL
    test_webhook = "https://discord.com/api/webhooks/test/test"
    
    notifier = DiscordNotifier(test_webhook, enabled=False)
    print("✓ Discord notifier initialized (disabled)")
    
    # テストデータ
    test_models = [
        {
            'id': 'test-model-1',
            'name': 'Test Model 1',
            'provider': 'Test Provider',
            'context_length': 8192,
            'weekly_tokens': 1000.0,
            'rank': 1
        }
    ]
    
    # 通知メソッドの呼び出し（実際には送信されない）
    notifier.send_top5_notification(test_models, {})
    print("✓ Top5 notification method called")
    
    notifier.send_new_models_notification(test_models)
    print("✓ New models notification method called")
    
    notifier.send_summary(5, 5000.0, 1)
    print("✓ Summary notification method called")

def test_config_loading():
    """設定ファイルの読み込みテスト"""
    print("\nTesting config loading...")
    
    import yaml
    from pathlib import Path
    
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        print("✓ Config file loaded successfully")
        print(f"  - Discord enabled: {config['discord']['enabled']}")
        print(f"  - Database path: {config['database']['path']}")
        print(f"  - API base URL: {config['api']['base_url']}")
    else:
        print("✗ Config file not found")

def main():
    """メインテスト関数"""
    print("=" * 60)
    print("OpenRouter Tracker - Test Suite")
    print("=" * 60)
    
    try:
        test_database_operations()
        test_discord_notifier()
        test_config_loading()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()