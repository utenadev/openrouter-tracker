#!/usr/bin/env python3
"""fetch_openrouter.pyのテスト - モックを使用したユニットテスト

外部APIへの依存を排除し、オフラインでも実行可能なテスト。
"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import yaml

from fetch_openrouter import extract_price
from fetch_openrouter import fetch_markdown
from fetch_openrouter import load_config
from fetch_openrouter import main
from fetch_openrouter import normalize_context
from fetch_openrouter import normalize_tokens
from fetch_openrouter import parse_markdown
from fetch_openrouter import setup_logging


class TestFetchOpenrouter:
    """fetch_openrouter.pyのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前のセットアップ"""
        self.test_db_path = Path(tempfile.mktemp(suffix=".db"))
        self.test_config = {
            "database": {"path": str(self.test_db_path)},
            "logging": {"file": "test.log", "level": "INFO"},
            "api": {
                "base_url": "https://r.jina.ai/https://openrouter.ai/models?fmt=table&max_price=0&order=top-weekly",
                "timeout": 30,
                "max_retries": 2,
                "retry_delay": 5,
                "user_agent": "test-agent",
            },
            "discord": {"webhook_url": "https://test-webhook", "enabled": False},
        }

    def teardown_method(self):
        """各テストメソッド実行後のクリーンアップ"""
        if self.test_db_path.exists():
            self.test_db_path.unlink()

    def test_normalize_tokens(self):
        """normalize_tokens関数のテスト"""
        assert normalize_tokens("1.2B") == 1200.0
        assert normalize_tokens("950M") == 950.0
        assert normalize_tokens("1000") == 1000.0
        assert normalize_tokens("1.5 B") == 1500.0
        assert normalize_tokens("2000 M") == 2000.0

    def test_normalize_context(self):
        """normalize_context関数のテスト"""
        assert normalize_context("32K") == 32768
        assert normalize_context("16K") == 16384
        assert normalize_context("1024") == 1024
        assert normalize_context("2K") == 2048

    def test_extract_price(self):
        """extract_price関数のテスト"""
        assert extract_price("$0.0001/M") == 0.0001
        assert extract_price("$0.0002/M") == 0.0002
        assert extract_price("$0.001/M") == 0.001
        assert extract_price("") == 0.0
        assert extract_price("invalid") == 0.0

    def test_parse_markdown(self):
        """parse_markdown関数のテスト"""
        mock_markdown = """
| Model Name | Input Price | Output Price | Context |
|------------|-------------|--------------|---------|
| [Mistral 7B](https://openrouter.ai/mistralai/Mistral-7B-Instruct-v0.1) | $0.0001/M | $0.0002/M | 32K |
| [Llama 2 7B](https://openrouter.ai/meta-llama/Llama-2-7b-chat) | $0.0001/M | $0.0002/M | 16K |

"""

        logger = logging.getLogger(__name__)
        models = parse_markdown(mock_markdown, logger)

        assert len(models) == 2
        assert models[0]["name"] == "Mistral 7B"
        assert models[0]["id"] == "mistralai/Mistral-7B-Instruct-v0.1"
        assert models[0]["provider"] == "Mistralai"
        assert models[0]["context_length"] == 32768
        assert models[0]["prompt_price"] == 0.0001
        assert models[0]["completion_price"] == 0.0002

    def test_parse_markdown_dynamic_headers(self):
        """動的ヘッダー解析のテスト"""
        mock_markdown = """
| Name | Price Input | Price Output | Length |
|------|-------------|--------------|--------|
| [Test Model](https://openrouter.ai/test/test-model) | $0.0001/M | $0.0002/M | 32K |

"""

        logger = logging.getLogger(__name__)
        models = parse_markdown(mock_markdown, logger)

        assert len(models) == 1
        assert models[0]["name"] == "Test Model"
        assert models[0]["id"] == "test/test-model"
        assert models[0]["provider"] == "Test"
        assert models[0]["context_length"] == 32768
        assert models[0]["prompt_price"] == 0.0001
        assert models[0]["completion_price"] == 0.0002

    @patch("fetch_openrouter.requests.get")
    def test_fetch_markdown_success(self, mock_get):
        """fetch_markdown関数の成功ケーステスト"""
        mock_response = Mock()
        mock_response.text = "test markdown content"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        logger = logging.getLogger(__name__)
        result = fetch_markdown(self.test_config, logger)

        assert result == "test markdown content"
        mock_get.assert_called_once()

    @patch("fetch_openrouter.requests.get")
    def test_fetch_markdown_with_retries(self, mock_get):
        """fetch_markdown関数のリトライ機能テスト"""
        mock_get.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            Mock(text="success", raise_for_status=lambda: None),
        ]

        logger = logging.getLogger(__name__)
        result = fetch_markdown(self.test_config, logger)

        assert result == "success"
        assert mock_get.call_count == 3

    def test_load_config_success(self):
        """load_config関数の正常系テスト"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(self.test_config, f)
            config_path = f.name

        try:
            config = load_config(config_path)
            assert config["database"]["path"] == str(self.test_db_path)
        finally:
            Path(config_path).unlink()

    def test_load_config_file_not_found(self):
        """load_config関数のファイル未検出エラーテスト"""
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    @patch("fetch_openrouter.fetch_markdown")
    @patch("fetch_openrouter.parse_markdown")
    @patch("fetch_openrouter.DiscordNotifier")
    def test_main_success(self, mock_notifier_class, mock_parse, mock_fetch):
        """main関数の正常系テスト"""
        # モックの設定
        mock_fetch.return_value = "test markdown"
        mock_parse.return_value = [
            {
                "id": "test-model",
                "name": "Test Model",
                "provider": "Test Provider",
                "context_length": 32768,
                "rank_score": 1000.0,
                "prompt_price": 0.0001,
                "completion_price": 0.0002,
            }
        ]
        mock_notifier_instance = Mock()
        mock_notifier_class.return_value = mock_notifier_instance

        # 一時的なconfigファイルを作成
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            temp_config = self.test_config.copy()
            temp_config["logging"] = self.test_config["logging"].copy()
            temp_config["logging"]["file"] = str(tempfile.mktemp(suffix=".log"))
            temp_config["logging"]["max_size_mb"] = 10
            temp_config["logging"]["backup_count"] = 5
            yaml.dump(temp_config, f)
            config_path = f.name

        try:
            # config.yamlを一時的に作成
            original_config = Path("config.yaml")
            if original_config.exists():
                original_config.rename("config.yaml.bak")

            Path("config.yaml").write_text(yaml.dump(temp_config))

            # main関数を実行
            main()

            # 後処理
            Path("config.yaml").unlink()
            if Path("config.yaml.bak").exists():
                Path("config.yaml.bak").rename("config.yaml")
        finally:
            Path(config_path).unlink()


def test_setup_logging():
    """setup_logging関数のテスト"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        config = {
            "logging": {
                "file": f.name,
                "level": "INFO",
                "max_size_mb": 10,
                "backup_count": 5,
            }
        }
        yaml.dump(config, f)
        config_path = f.name

    try:
        logger = setup_logging(config)
        assert logger is not None
        assert logger.level == logging.INFO
    finally:
        Path(config_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__])
