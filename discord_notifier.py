import logging
import os
import time
from datetime import datetime
from typing import TypedDict

import requests

logger = logging.getLogger(__name__)


class ModelRanking(TypedDict):
    id: str
    name: str
    provider: str
    context_length: int
    rank_score: float
    rank: int


class NewModel(TypedDict):
    id: str
    name: str
    provider: str
    context_length: int
    rank_score: float


class DiscordNotifier:
    def __init__(self, webhook_url: str | None = None, enabled: bool = True):
        # Prioritize environment variable if set
        env_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        self.webhook_url = env_webhook_url if env_webhook_url else webhook_url

        # Also support disabling via environment variable
        env_disabled = os.environ.get("DISCORD_NOTIFIER_DISABLED", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        self.enabled = not env_disabled and enabled

    def send_top5_notification(
        self, models: list[dict], previous_rankings: dict[str, int]
    ):
        """Send top 5 models notification"""
        if not self.enabled:
            logger.info("Discord notifications are disabled")
            return

        today = datetime.now().strftime("%Y-%m-%d")

        embed = {
            "title": "📊 OpenRouter Free Model Weekly Rankings Top 5",
            "description": f"📅 {today}",
            "color": 0x5865F2,
            "fields": [],
        }

        for i, model in enumerate(models[:5], 1):
            prev_rank = previous_rankings.get(
                model["id"], i
            )  # Assume current rank if no data
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

            # Format rank score
            rank_score = model["rank_score"]
            if rank_score >= 1000:
                score_str = f"{rank_score / 1000:.2f}B"
            else:
                score_str = f"{rank_score:.1f}M"

            # Format context length
            context = model["context_length"]
            if context >= 1024:
                context_str = f"{context // 1024}K"
            else:
                context_str = str(context)

            field = {
                "name": f"{i}. {model['name']}",
                "value": f"🔸 Rank Score: {score_str}\n"
                f"📈 Previous Rank: {change_text} {change_emoji}\n"
                f"📏 Context: {context_str}",
                "inline": False,
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_new_models_notification(self, new_models: list[dict]):
        """Send new model addition notification"""
        if not self.enabled or not new_models:
            return

        embed = {
            "title": "🆕 New models have been added",
            "color": 0x00FF00,
            "fields": [],
        }

        for model in new_models:
            field = {
                "name": model["name"],
                "value": f"Provider: {model['provider']}\n"
                f"Context: {model['context_length']:,}",
                "inline": False,
            }
            embed["fields"].append(field)

        self.send_embed(embed)

    def send_summary(
        self, total_models: int, total_tokens: float, new_models_count: int
    ):
        """Send statistical summary notification"""
        if not self.enabled:
            return

        if total_tokens >= 1000:
            score_str = f"{total_tokens / 1000:.2f}B"
        else:
            score_str = f"{total_tokens:.1f}M"

        embed = {
            "title": "📊 Statistical Summary",
            "color": 0x1E88E5,
            "fields": [
                {"name": "Total Models", "value": str(total_models), "inline": True},
                {"name": "Total Rank Score", "value": score_str, "inline": True},
                {
                    "name": "Added Models",
                    "value": str(new_models_count),
                    "inline": True,
                },
            ],
        }

        self.send_embed(embed)

    def send_embed(self, embed: dict):
        """Send embed message"""
        payload = {"embeds": [embed]}

        try:
            time.sleep(1)  # Rate limit protection
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Discord notification sent successfully")
        except Exception as e:
            logger.error("Failed to send Discord notification: %s", e)
            # Add retry logic
            time.sleep(2)
            try:
                response = requests.post(self.webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info("Discord notification sent successfully on retry")
            except Exception as e:
                logger.error("Failed to send Discord notification on retry: %s", e)
                raise
