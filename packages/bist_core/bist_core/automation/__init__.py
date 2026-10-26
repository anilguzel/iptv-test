"""Scheduled automation: collect daily bars into a CSV store, run the weekly
research on the stored history, and send Telegram summaries.

Designed for GitHub Actions (see .github/workflows/) but runs anywhere:
``python -m bist_core.automation collect|research --config automation/jobs.json --store store``.
"""
