from __future__ import annotations

import os
from typing import Any

import httpx


class DiscordNotifier:
    def __init__(self) -> None:
        self._webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

    def notify_qa_result(
        self,
        *,
        idea_title: str,
        idea_record_id: str,
        qa_status: str,
        qa_score: int,
        qa_findings: str,
        airtable_url: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        color = {
            "PASS": 0x2ECC71,
            "FAIL": 0xE74C3C,
            "要承認": 0x3498DB,
        }.get(qa_status, 0x95A5A6)
        fields: list[dict[str, Any]] = [
            {"name": "qa_status", "value": qa_status, "inline": True},
            {"name": "qa_score", "value": str(qa_score), "inline": True},
            {"name": "idea_id", "value": f"`{idea_record_id}`", "inline": True},
        ]
        if airtable_url:
            fields.append({"name": "Airtable", "value": airtable_url, "inline": False})
        embed: dict[str, Any] = {
            "title": f"Instagram QA: {idea_title}",
            "description": qa_findings[:1800] if qa_findings else "(所見なし)",
            "color": color,
            "fields": fields,
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self._webhook_url, json={"embeds": [embed]})
            resp.raise_for_status()

    def notify_run_summary(
        self,
        *,
        processed: int,
        pass_count: int,
        fail_count: int,
        review_count: int,
        errors: int,
    ) -> None:
        if not self.enabled:
            return
        embed = {
            "title": "Instagram QA バッチ完了",
            "color": 0x3498DB,
            "fields": [
                {"name": "対象", "value": str(processed), "inline": True},
                {"name": "PASS", "value": str(pass_count), "inline": True},
                {"name": "FAIL", "value": str(fail_count), "inline": True},
                {"name": "要承認", "value": str(review_count), "inline": True},
                {"name": "エラー", "value": str(errors), "inline": True},
            ],
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self._webhook_url, json={"embeds": [embed]})
            resp.raise_for_status()
