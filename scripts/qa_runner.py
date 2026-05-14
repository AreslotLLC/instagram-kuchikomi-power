from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from scripts.airtable_client import KuchikomiAirtable  # noqa: E402
from scripts.discord_notifier import DiscordNotifier  # noqa: E402
from scripts.vision_qa import VisionQA  # noqa: E402


def _airtable_record_url(base_id: str, table_id: str, record_id: str) -> str:
    return f"https://airtable.com/{base_id}/{table_id}/{record_id}"


def _build_idea_payload(idea: dict[str, Any], slides: list[dict[str, Any]]) -> dict[str, Any]:
    f = idea["fields"]
    return {
        "idea_id": idea["id"],
        "title": f.get("title", ""),
        "overview": f.get("overview", ""),
        "caption": f.get("caption", ""),
        "hashtags": f.get("hashtags", ""),
        "slides": [
            {
                "slide_id": s["id"],
                "slide_number": s["fields"].get("slide_number", 0),
                "slide_title": s["fields"].get("slide_title", ""),
                "image_description": s["fields"].get("image_description", ""),
                "generated_image_url": s["fields"].get("generated_image_url", ""),
            }
            for s in slides
        ],
    }


def _resolve_qa_status(result: dict[str, Any], threshold: int) -> str:
    declared = result.get("qa_status", "").strip()
    if declared in {"PASS", "FAIL", "要承認"}:
        return declared
    score = int(result.get("qa_score", 0))
    if score >= threshold:
        return "PASS"
    if score < 50:
        return "FAIL"
    return "要承認"


def run(limit: int | None, dry_run: bool) -> int:
    target_status = os.environ.get("QA_TARGET_STATUS", "投稿待ち")
    threshold = int(os.environ.get("QA_PASS_THRESHOLD", "80"))
    max_attempts = int(os.environ.get("QA_MAX_ATTEMPTS", "3"))

    air = KuchikomiAirtable()
    discord = DiscordNotifier()
    vision = VisionQA() if not dry_run else None

    ideas = air.fetch_ideas_pending_qa(target_status, limit=limit)
    print(f"[info] target ideas: {len(ideas)}", file=sys.stderr)

    counts = {"PASS": 0, "FAIL": 0, "要承認": 0}
    errors = 0

    for idx, idea in enumerate(ideas, start=1):
        idea_id = idea["id"]
        title = idea["fields"].get("title", "(no title)")
        prev_attempts = int(idea["fields"].get("qa_attempt_no", 0) or 0)
        attempt_no = prev_attempts + 1
        print(f"[{idx}/{len(ideas)}] {idea_id} {title} attempt={attempt_no}", file=sys.stderr)

        try:
            slides = air.fetch_slides_for_idea(idea_id)
            payload = _build_idea_payload(idea, slides)
            if dry_run:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                continue

            air.mark_idea_qa_in_progress(idea_id)
            result = vision.evaluate_idea(payload)

            qa_status = _resolve_qa_status(result, threshold)
            if qa_status == "FAIL" and attempt_no >= max_attempts:
                qa_status = "要承認"
            qa_score = int(result.get("qa_score", 0))
            qa_findings = result.get("qa_findings", "")

            air.update_idea_qa(
                idea_id,
                qa_status=qa_status,
                qa_score=qa_score,
                qa_findings=qa_findings,
                qa_attempt_no=attempt_no,
            )
            for slide_result in result.get("slides", []):
                sid = slide_result.get("slide_id")
                if not sid:
                    continue
                air.update_slide_qa(
                    sid,
                    slide_qa_status=slide_result.get("slide_qa_status", "未検査"),
                    slide_qa_score=int(slide_result.get("slide_qa_score", 0)),
                    slide_qa_findings=slide_result.get("slide_qa_findings", ""),
                )

            counts[qa_status] = counts.get(qa_status, 0) + 1
            discord.notify_qa_result(
                idea_title=title,
                idea_record_id=idea_id,
                qa_status=qa_status,
                qa_score=qa_score,
                qa_findings=qa_findings,
                airtable_url=_airtable_record_url(air.base_id, air.ideas_table_id, idea_id),
            )
            print(f"  -> {qa_status} score={qa_score}", file=sys.stderr)

        except Exception:  # noqa: BLE001
            errors += 1
            traceback.print_exc()

    if not dry_run:
        discord.notify_run_summary(
            processed=len(ideas),
            pass_count=counts.get("PASS", 0),
            fail_count=counts.get("FAIL", 0),
            review_count=counts.get("要承認", 0),
            errors=errors,
        )
    print(f"[done] {counts} errors={errors}", file=sys.stderr)
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Instagram カルーセルQAバッチ実行")
    parser.add_argument("--limit", type=int, default=None, help="処理件数の上限")
    parser.add_argument("--dry-run", action="store_true", help="Airtable取得とpayload組み立てまで")
    args = parser.parse_args()
    sys.exit(run(limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
