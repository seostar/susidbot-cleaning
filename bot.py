name: Cleaner Bot

on:
  schedule:
    - cron: '10 19 * * *'  # 21:10 за Києвом (19:10 UTC)
  workflow_dispatch:      # Дозволяє запускати вручну кнопкою

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install pyTelegramBotAPI pytz

      - name: Run bot
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          CHAT_ID: ${{ secrets.CHAT_ID }}
          THREAD_ID: ${{ secrets.THREAD_ID }}
        run: python bot.py

      - name: Commit history
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git add history.json
          git commit -m "Update payment history" || echo "No changes to commit"
          git push
