#!/usr/bin/env python3
"""discord_notifier.pyのテスト - モックを使用したユニットテスト

Discord通知機能のテストで外部APIへの依存を排除。
"""

from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests

from discord_notifier import DiscordNotifier


class TestDiscordNotifier:
    """DiscordNotifierクラスのテスト"""

    def setup_method(self):
        """各テストメソッド実行前のセットアップ"""
        self.webhook_url = "https://discord.com/api/webhooks/test/test"
        self.notifier = DiscordNotifier(webhook_url=self.webhook_url, enabled=True)

    @patch("discord_notifier.requests.post")
    def test_send_top5_notification_success(self, mock_post):
        """トップ5通知の成功ケーステスト"""
        # モックの設定
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        models = [
            {
                "name": "Model 1",
                "rank_score": 1000.0,
                "context_length": 32768,
                "id": "model-1",
            },
            {
                "name": "Model 2",
                "rank_score": 900.0,
                "context_length": 16384,
                "id": "model-2",
            },
        ]
        previous_rankings = {"model-1": 2, "model-2": 1}  # 前回のランキング

        self.notifier.send_top5_notification(models, previous_rankings)

        # リクエストが送信されたことを確認
        assert mock_post.called
        assert mock_post.call_count == 1

        # ペイロードを確認
        call_args = mock_post.call_args
        assert call_args[1]["json"] is not None
        payload = call_args[1]["json"]
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1

        embed = payload["embeds"][0]
        assert "Top 5" in embed["title"]
        assert len(embed["fields"]) == 2  # 2つのモデル

    @patch("discord_notifier.requests.post")
    def test_send_new_models_notification_success(self, mock_post):
        """新規モデル通知の成功ケーステスト"""
        # モックの設定
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        new_models = [
            {
                "name": "New Model",
                "provider": "New Provider",
                "context_length": 32768,
            }
        ]

        self.notifier.send_new_models_notification(new_models)

        # リクエストが送信されたことを確認
        assert mock_post.called

        # ペイロードを確認
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert "New models" in embed["title"]

    @patch("discord_notifier.requests.post")
    def test_send_summary_success(self, mock_post):
        """サマリー通知の成功ケーステスト"""
        # モックの設定
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        self.notifier.send_summary(
            total_models=10, total_tokens=5000.0, new_models_count=2
        )

        # リクエストが送信されたことを確認
        assert mock_post.called

        # ペイロードを確認
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert "Summary" in embed["title"]
        assert len(embed["fields"]) == 3  # Total Models, Total Rank Score, Added Models

    @patch("discord_notifier.requests.post")
    def test_send_notification_with_retry(self, mock_post):
        """通知のリトライ機能テスト"""
        # 最初は失敗、リトライで成功
        mock_post.side_effect = [
            requests.exceptions.RequestException("Network error"),
            Mock(raise_for_status=lambda: None),
        ]

        models = [
            {
                "name": "Test Model",
                "rank_score": 1000.0,
                "id": "test-model",
                "context_length": 32768,
            }
        ]
        previous_rankings = {}

        self.notifier.send_top5_notification(models, previous_rankings)

        # 2回呼び出されていることを確認（1回失敗 + 1回リトライ）
        assert mock_post.call_count == 2

    @patch("discord_notifier.requests.post")
    def test_send_notification_retry_failure(self, mock_post):
        """通知のリトライ失敗テスト"""
        # すべての試行で失敗
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        models = [
            {
                "name": "Test Model",
                "rank_score": 1000.0,
                "id": "test-model",
                "context_length": 32768,
            }
        ]
        previous_rankings = {}

        # 例外が発生することを確認
        with pytest.raises(requests.exceptions.RequestException):
            self.notifier.send_top5_notification(models, previous_rankings)

        # 2回（初期 + リトライ）呼び出されていることを確認
        assert mock_post.call_count == 2

    def test_notifier_disabled(self):
        """通知が無効化されている場合のテスト"""
        disabled_notifier = DiscordNotifier(webhook_url=self.webhook_url, enabled=False)

        # モック化されたrequests.postを準備
        with patch("discord_notifier.requests.post") as mock_post:
            models = [{"name": "Test Model", "rank_score": 1000.0, "id": "test-model"}]
            previous_rankings = {}

            disabled_notifier.send_top5_notification(models, previous_rankings)

            # リクエストが送信されていないことを確認
            assert not mock_post.called

    def test_notifier_with_env_vars(self):
        """環境変数を使用した初期化テスト"""
        import os

        # 環境変数を設定
        os.environ["DISCORD_WEBHOOK_URL"] = "https://env-webhook-url"
        os.environ["DISCORD_NOTIFIER_DISABLED"] = "true"

        try:
            notifier = DiscordNotifier(webhook_url="fallback-url")
            assert notifier.webhook_url == "https://env-webhook-url"
            assert notifier.enabled is False
        finally:
            # 環境変数をクリーンアップ
            del os.environ["DISCORD_WEBHOOK_URL"]
            del os.environ["DISCORD_NOTIFIER_DISABLED"]

    def test_notifier_env_vars_false(self):
        """環境変数がfalseの場合のテスト"""
        import os

        # 環境変数を設定
        os.environ["DISCORD_NOTIFIER_DISABLED"] = "false"

        try:
            notifier = DiscordNotifier(webhook_url=self.webhook_url, enabled=True)
            assert notifier.enabled is True
        finally:
            # 環境変数をクリーンアップ
            del os.environ["DISCORD_NOTIFIER_DISABLED"]

    @patch("discord_notifier.requests.post")
    def test_send_embed_success(self, mock_post):
        """埋め込みメッセージ送信の成功テスト"""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        test_embed = {"title": "Test Embed", "description": "Test Description"}

        self.notifier.send_embed(test_embed)

        # リクエストが送信されたことを確認
        assert mock_post.called
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        assert payload["embeds"] == [test_embed]

    @patch("discord_notifier.time.sleep")
    @patch("discord_notifier.requests.post")
    def test_rate_limit_protection(self, mock_post, mock_sleep):
        """レート制限保護のテスト"""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        test_embed = {"title": "Test Embed", "description": "Test Description"}

        self.notifier.send_embed(test_embed)

        # time.sleepが呼ばれたことを確認（レート制限対策）
        mock_sleep.assert_called_once_with(1)

    def test_notifier_with_none_webhook(self):
        """webhook_urlがNoneの場合のテスト"""
        notifier = DiscordNotifier(webhook_url=None, enabled=False)
        assert notifier.webhook_url is None
        assert notifier.enabled is False


if __name__ == "__main__":
    pytest.main([__file__])
