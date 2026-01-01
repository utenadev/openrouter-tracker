import logging
import time
from datetime import datetime
from typing import Dict
from typing import List

import requests

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self, webhook_url: str, enabled: bool = True):
        self.webhook_url = webhook_url
        self.enabled = enabled

    def send_top5_notification(
        self, models: List[Dict], previous_rankings: Dict[str, int]
    ):
        """トップ5モデルの通知を送信"""
        if not self.enabled:
            logger.info("Discord notifications are disabled")
            return

        today = datetime.now().strftime("%Y-%m-%d")

        embed = {
            "title": "📊 OpenRouter 無料モデル 週間ランキング Top 5",
            "description": f"📅 {today}",
            "color": 0x5865F2,
            "fields": []
        }

        for i, model in enumerate(models[:5], 1):
            prev_rank = previous_rankings.get(
                model["id"], i
            )  # データがない場合は現在の順位と仮定
            change = prev_rank - i

            if change > 0:
                change_emoji = "📈"
                change_text = f"#{prev_rank} → #{i} (+{change})"
            elif change < 0:
                change_emoji = "📉"
                change_text = f"#{prev_rank} → #{i} ({change})"
            else:
                change_emoji = "➡️"
                change_text = f"#{i}"

            # トークン数をフォーマット
            weekly_tokens = model["weekly_tokens"]
            if weekly_tokens >= 1000:
                tokens_str = f"{weekly_tokens/1000:.2f}B"
            else:
                tokens_str = f"{weekly_tokens:.1f}M"

            # コンテキスト長をフォーマット
            context = model["context_length"]
            if context >= 1024:
                context_str = f"{context//1024}K"
            else:
                context_str = str(context)

            field = {
                "name": f"{i}. {model['name']}",
                "value": f"🔸 週間トークン: {tokens_str}\n"
                        f"📈 前日順位: {change_text} {change_emoji}\n"
                        f"📏 コンテキスト: {context_str}",
                "inline": False
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_new_models_notification(self, new_models: List[Dict]):
        """新規追加モデルの通知"""
        if not self.enabled or not new_models:
            return

        embed = {
            "title": "🆕 新しいモデルが追加されました",
            "color": 0x00FF00,
            "fields": []
        }

        for model in new_models:
            field = {
                "name": model["name"],
                "value": f"プロバイダー: {model['provider']}\n"
                        f"コンテキスト: {model['context_length']:,}",
                "inline": False
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_summary(
        self, total_models: int, total_tokens: float, new_models_count: int
    ):
        """統計サマリーの通知"""
        if not self.enabled:
            return

        if total_tokens >= 1000:
            tokens_str = f"{total_tokens/1000:.2f}B"
        else:
            tokens_str = f"{total_tokens:.1f}M"

        embed = {
            "title": "📊 統計サマリー",
            "color": 0x1E88E5,
            "fields": [
                {
                    "name": "総モデル数",
                    "value": str(total_models),
                    "inline": True
                },
                {
                    "name": "今週の総トークン",
                    "value": tokens_str,
                    "inline": True
                },
                {
                    "name": "追加されたモデル",
                    "value": str(new_models_count),
                    "inline": True
                }
            ]
        }

        self.send_embed(embed)

    def send_embed(self, embed: Dict):
        """埋め込みメッセージを送信"""
        payload = {"embeds": [embed]}

        try:
            time.sleep(1)  # レート制限対策
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
        except Exception as e:
            logger.error("Failed to send Discord notification: %s", e)
            # リトライロジックを追加
            time.sleep(2)
            try:
                response = requests.post(self.webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Discord notification sent successfully on retry")
            except Exception as e:
                logger.error("Failed to send Discord notification on retry: %s", e)
