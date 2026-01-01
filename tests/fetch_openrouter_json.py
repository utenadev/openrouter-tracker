#!/usr/bin/env python3
"""OpenRouter APIからJSON形式でデータを取得するスクリプト"""

import json
from pathlib import Path
from typing import Dict
from typing import List

import requests
import yaml

# 定数定義
BASE_DIR = Path(__file__).parent.resolve()

def load_config(config_path: str = "config.yaml") -> Dict:
    """設定ファイルの読み込み"""
    abs_config_path = BASE_DIR / config_path

    with open(abs_config_path) as f:
        config = yaml.safe_load(f)

    return config

def fetch_json_data(config: Dict) -> Dict:
    """OpenRouter APIからJSONデータを取得"""
    url = "https://openrouter.ai/api/v1/models"

    headers = {
        "User-Agent": config["api"]["user_agent"]
    }

    params = {
        "max_price": 0
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=config["api"]["timeout"]
        )
        response.raise_for_status()

        return response.json()
    except Exception as e:
        print(f"Failed to fetch JSON data: {e}")
        return {}

def extract_free_models(json_data: Dict) -> List[Dict]:
    """JSONデータからFreeモデルを抽出"""
    free_models = []

    if "data" not in json_data:
        return free_models

    for model in json_data["data"]:
        # Freeモデルのみを抽出
        if model.get("pricing", {}).get("prompt") == 0 and model.get("pricing", {}).get("completion") == 0:
            free_models.append({
                "id": model["id"],
                "name": model.get("name", "Unknown"),
                "context_length": model.get("context_length", 0),
                "created_at": model.get("created_at", ""),
                "updated_at": model.get("updated_at", ""),
                "provider": model.get("provider", "Unknown")
            })

    return free_models

def compare_models(current_models: List[Dict], previous_models: List[Dict]) -> Dict:
    """モデルの増減を比較"""
    current_ids = {m["id"] for m in current_models}
    previous_ids = {m["id"] for m in previous_models}

    new_models = [m for m in current_models if m["id"] not in previous_ids]
    removed_models = [m for m in previous_models if m["id"] not in current_ids]

    return {
        "new": new_models,
        "removed": removed_models
    }

def save_model_list(models: List[Dict], filename: str = "free_models.json"):
    """モデルリストを保存"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(models, f, indent=2, ensure_ascii=False)

def load_model_list(filename: str = "free_models.json") -> List[Dict]:
    """モデルリストを読み込み"""
    try:
        with open(filename, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def main():
    """メイン処理"""
    print("Fetching Free LLM information from OpenRouter API...")

    # 設定読み込み
    config = load_config()

    # JSONデータの取得
    json_data = fetch_json_data(config)

    if not json_data:
        print("Failed to fetch JSON data")
        return

    # Freeモデルの抽出
    current_models = extract_free_models(json_data)
    print(f"Found {len(current_models)} free models")

    # 前回のモデルリストを読み込み
    previous_models = load_model_list()
    print(f"Previous: {len(previous_models)} free models")

    # モデルの比較
    comparison = compare_models(current_models, previous_models)

    # 結果の表示
    if comparison["new"]:
        print(f"\n🆕 New models ({len(comparison['new'])}):")
        for model in comparison["new"]:
            print(f"  - {model['name']} ({model['provider']})")

    if comparison["removed"]:
        print(f"\n🗑️ Removed models ({len(comparison['removed'])}):")
        for model in comparison["removed"]:
            print(f"  - {model['name']} ({model['provider']})")

    if not comparison["new"] and not comparison["removed"]:
        print("\n✓ No changes in free models")

    # モデルリストの保存
    save_model_list(current_models)
    print("\n✓ Free model list saved")

if __name__ == "__main__":
    main()
