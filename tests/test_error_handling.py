#!/usr/bin/env python3
"""異常系テスト - APIエラー時の挙動を確認"""

import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from fetch_openrouter import fetch_markdown
import logging

class TestErrorHandling(unittest.TestCase):
    """エラーハンドリングのテスト"""
    
    def setUp(self):
        """テストの準備"""
        self.config = {
            'api': {
                'base_url': 'https://example.com/api',
                'timeout': 30,
                'max_retries': 2,
                'retry_delay': 5,
                'user_agent': 'Test User Agent'
            }
        }
        self.logger = logging.getLogger(__name__)
    
    @patch('requests.get')
    def test_fetch_markdown_timeout(self, mock_get):
        """タイムアウトエラーのテスト"""
        # タイムアウトエラーを発生させる
        mock_get.side_effect = Exception('Connection timeout')
        
        # エラーが発生することを確認
        with self.assertRaises(RuntimeError) as context:
            fetch_markdown(self.config, self.logger)
        
        # エラーメッセージを確認
        self.assertIn('Failed after 3 attempts', str(context.exception))
        
        # リトライが行われていることを確認
        self.assertEqual(mock_get.call_count, 3)
    
    @patch('requests.get')
    def test_fetch_markdown_empty_response(self, mock_get):
        """空のレスポンスのテスト"""
        # 空のレスポンスを返す
        mock_response = MagicMock()
        mock_response.text = ''
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # エラーが発生することを確認
        with self.assertRaises(ValueError) as context:
            fetch_markdown(self.config, self.logger)
        
        # エラーメッセージを確認
        self.assertIn('Empty response from API', str(context.exception))
    
    @patch('requests.get')
    def test_fetch_markdown_http_error(self, mock_get):
        """HTTPエラーのテスト"""
        # HTTPエラーを発生させる
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception('HTTP Error 404')
        mock_get.return_value = mock_response
        
        # エラーが発生することを確認
        with self.assertRaises(RuntimeError) as context:
            fetch_markdown(self.config, self.logger)
        
        # エラーメッセージを確認
        self.assertIn('Failed after 3 attempts', str(context.exception))
    
    @patch('requests.get')
    def test_fetch_markdown_success(self, mock_get):
        """正常系のテスト"""
        # 正常なレスポンスを返す
        mock_response = MagicMock()
        mock_response.text = '*   [Test Model](https://example.com/test) 100M tokens'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # 正常にデータが取得できることを確認
        result = fetch_markdown(self.config, self.logger)
        
        # データが取得されていることを確認
        self.assertIn('Test Model', result)

if __name__ == '__main__':
    unittest.main()