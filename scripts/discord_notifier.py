from __future__ import annotations

import os

import httpx


class DiscordNotifier:
    def __init__(self) -> None:
        self._webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self._webhook_url)

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
        if fail_count == 0 and review_count == 0:
            return  # 全件PASS・エラーなしは通知不要

        parts = []
        if fail_count:
            parts.append(f"FAIL {fail_count}件")
        if review_count:
            parts.append(f"要承認 {review_count}件")
        if errors:
            parts.append(f"エラー {errors}件")

        content = f"Instagram QA完了（{processed}件中）：{' / '.join(parts)}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(self._webhook_url, json={"content": content})
            resp.raise_for_status()
