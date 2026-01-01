#!/bin/bash
set -e

echo "Setting up openrouter-tracker..."

# ディレクトリ作成
mkdir -p ~/openrouter-tracker/logs

# 仮想環境の作成（推奨）
cd ~/openrouter-tracker
python3 -m venv venv

# .gitignoreの作成
echo "venv/" > .gitignore
echo "__pycache__/" >> .gitignore
echo "*.db" >> .gitignore
echo "config.yaml" >> .gitignore
echo "logs/" >> .gitignore

# 依存ライブラリのインストール
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# config.yamlの作成（まだ存在しない場合）
if [ ! -f config.yaml ]; then
    echo "config.yaml not found. Please create it manually."
fi

# スクリプトの実行権限設定
chmod +x fetch_openrouter.py

# データベースの初期化
./venv/bin/python3 -c "from db import Database; db = Database('models.db'); db.__enter__(); db.init_db()"

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.yaml with your Discord webhook URL"
echo "2. Run: ./venv/bin/python3 fetch_openrouter.py"
echo "3. Add to crontab: crontab -e"