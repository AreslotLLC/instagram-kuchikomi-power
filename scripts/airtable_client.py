from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any

from pyairtable import Api


JST = timezone(timedelta(hours=9))


def _now_jst_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


class KuchikomiAirtable:
    def __init__(self) -> None:
        pat = os.environ["AIRTABLE_PAT"]
        self.base_id = os.environ["AIRTABLE_BASE_ID"]
        self.ideas_table_id = os.environ["AIRTABLE_TABLE_IDEAS"]
        self.slides_table_id = os.environ["AIRTABLE_TABLE_SLIDES"]
        self._api = Api(pat)
        self._ideas = self._api.table(self.base_id, self.ideas_table_id)
        self._slides = self._api.table(self.base_id, self.slides_table_id)

    def fetch_ideas_pending_qa(self, target_status: str, limit: int | None = None) -> list[dict[str, Any]]:
        formula = f"{{status}}='{target_status}'"
        records = self._ideas.all(formula=formula, sort=["投稿順", "投稿予定日"])
        if limit is not None:
            records = records[:limit]
        return records

    def fetch_slides_for_idea(self, idea_record_id: str) -> list[dict[str, Any]]:
        # instagram_content はリンクフィールドのため ARRAYJOIN が表示名を返してIDと一致しない。
        # idea_record_id_lookup（レコードIDを保持するLookupフィールド）を使う。
        formula = f"FIND('{idea_record_id}', ARRAYJOIN({{idea_record_id_lookup}}))"
        records = self._slides.all(formula=formula, sort=["slide_number"])
        return records

    def update_idea_qa(
        self,
        idea_record_id: str,
        *,
        qa_status: str,
        qa_score: int,
        qa_findings: str,
        qa_attempt_no: int,
    ) -> None:
        self._ideas.update(
            idea_record_id,
            {
                "qa_status": qa_status,
                "qa_score": qa_score,
                "qa_findings": qa_findings,
                "qa_checked_at": _now_jst_iso(),
                "qa_attempt_no": qa_attempt_no,
            },
        )

    def mark_idea_qa_in_progress(self, idea_record_id: str) -> None:
        self._ideas.update(idea_record_id, {"qa_status": "検査中"})

    def update_slide_qa(
        self,
        slide_record_id: str,
        *,
        slide_qa_status: str,
        slide_qa_score: int,
        slide_qa_findings: str,
    ) -> None:
        new_status = "投稿待ち" if slide_qa_status == "PASS" else "再生成待ち"
        self._slides.update(
            slide_record_id,
            {
                "slide_qa_status": slide_qa_status,
                "slide_qa_score": slide_qa_score,
                "slide_qa_findings": slide_qa_findings,
                "slide_qa_checked_at": _now_jst_iso(),
                "status": new_status,
            },
        )

    def update_slide_description(
        self,
        slide_record_id: str,
        *,
        slide_title: str,
        image_description: str,
    ) -> None:
        updates: dict[str, Any] = {"image_description": image_description}
        if slide_title.strip():
            updates["slide_title"] = slide_title
        self._slides.update(slide_record_id, updates)

    def promote_idea_if_all_slides_pass(self, idea_record_id: str) -> bool:
        """全スライドが PASS なら idea の status を '投稿待ち' に昇格する。"""
        slides = self.fetch_slides_for_idea(idea_record_id)
        if not slides:
            return False
        all_pass = all(
            s["fields"].get("slide_qa_status") == "PASS" for s in slides
        )
        if all_pass:
            self._ideas.update(idea_record_id, {"status": "投稿待ち"})
        return all_pass
