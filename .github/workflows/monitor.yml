name: Master Monitor
on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests pyyaml

      - name: Run monitor
        env:
          GITHUB_TOKEN: ${{ secrets.MONITOR_GITHUB_TOKEN }}
        run: python monitor.py

      - name: Commit dashboard results
        run: |
          git config user.name  "Master Monitor"
          git config user.email "monitor@lexplair.com"
          git remote set-url origin https://x-access-token:${{ secrets.MONITOR_GITHUB_TOKEN }}@github.com/nobill77/master-monitor.git
          git add dashboard/results.json
          git diff --staged --quiet || git commit -m "📊 Monitor: update results $(date -u '+%H:%M UTC')"
          git push origin HEAD:main
