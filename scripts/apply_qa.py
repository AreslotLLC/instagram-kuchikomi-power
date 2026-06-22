"""Claude Code セッションが生成した QA 判定結果 JSON を読み、
Airtable に書き戻し、Discord に通知する。

入力 JSON フォーマット:
{
  "results": [
    {
      "idea_id": "recXXXX",
      "title": "...",
      "qa_status": "PASS | FAIL | 要承認",
      "qa_score": 0-100,
      "qa_findings": "Markdown所見",
      "qa_attempt_no_prev": <number>,
      "slides": [
        {"slide_id": "recXXXX", "slide_qa_status": "...",
         "slide_qa_score": 0-100, "slide_qa_findings": "..."}
      ]
    }
  ]
}
"""

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



def _resolve_qa_status(declared: str, score: int, threshold: int) -> str:
    if declared in {"PASS", "FAIL", "要承認"}:
        return declared
    if score >= threshold:
        return "PASS"
    if score < 50:
        return "FAIL"
    return "要承認"


def apply_results(input_path: Path) -> int:
    threshold = int(os.environ.get("QA_PASS_THRESHOLD", "80"))
    max_attempts = int(os.environ.get("QA_MAX_ATTEMPTS", "3"))

    data = json.loads(input_path.read_text(encoding="utf-8"))
    results = data.get("results", [])

    air = KuchikomiAirtable()
    discord = DiscordNotifier()

    counts: dict[str, int] = {"PASS": 0, "FAIL": 0, "要承認": 0}
    errors = 0

    for idx, item in enumerate(results, start=1):
        idea_id = item["idea_id"]
        title = item.get("title", "(no title)")
        prev_attempts = int(item.get("qa_attempt_no_prev", 0) or 0)
        attempt_no = prev_attempts + 1

        try:
            qa_score = int(item.get("qa_score", 0))
            qa_status = _resolve_qa_status(
                item.get("qa_status", ""), qa_score, threshold
            )
            if qa_status == "FAIL" and attempt_no >= max_attempts:
                qa_status = "要承認"
            qa_findings = item.get("qa_findings", "")

            air.update_idea_qa(
                idea_id,
                qa_status=qa_status,
                qa_score=qa_score,
                qa_findings=qa_findings,
                qa_attempt_no=attempt_no,
            )
            for s in item.get("slides", []):
                sid = s.get("slide_id")
                if not sid:
                    continue
                air.update_slide_qa(
                    sid,
                    slide_qa_status=s.get("slide_qa_status", "未検査"),
                    slide_qa_score=int(s.get("slide_qa_score", 0)),
                    slide_qa_findings=s.get("slide_qa_findings", ""),
                )

            promoted = air.promote_idea_if_all_slides_pass(idea_id)
            if promoted:
                print(
                    f"[apply] {idea_id} → idea status promoted to 投稿待ち",
                    file=sys.stderr,
                )

            counts[qa_status] = counts.get(qa_status, 0) + 1
            print(
                f"[apply] {idx}/{len(results)} {idea_id} -> {qa_status} score={qa_score}",
                file=sys.stderr,
            )

        except Exception:  # noqa: BLE001
            errors += 1
            traceback.print_exc()

    discord.notify_run_summary(
        processed=len(results),
        pass_count=counts.get("PASS", 0),
        fail_count=counts.get("FAIL", 0),
        review_count=counts.get("要承認", 0),
        errors=errors,
    )
    print(f"[apply][done] {counts} errors={errors}", file=sys.stderr)
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply QA results back to Airtable + Discord")
    parser.add_argument("--input", type=Path, default=Path("/tmp/qa_results.json"))
    args = parser.parse_args()
    sys.exit(apply_results(args.input))


if __name__ == "__main__":
    main()
