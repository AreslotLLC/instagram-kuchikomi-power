"""image_description 未記入の「生成待ち」スライドを取得して JSON で吐き出す。

Routine 内で実行され、後続の Claude Code セッション本体が
この JSON をサブエージェントに渡して image_description を生成させる。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from scripts.airtable_client import KuchikomiAirtable  # noqa: E402


GEN_TARGET_SLIDE_STATUS = "生成待ち"


def _slide_needs_description(sfields: dict[str, Any]) -> bool:
    if sfields.get("status", "") != GEN_TARGET_SLIDE_STATUS:
        return False
    return not str(sfields.get("image_description", "") or "").strip()


def build_gen_pending_payload(
    *,
    limit: int | None,
    target_idea_status: str,
) -> dict[str, Any]:
    air = KuchikomiAirtable()
    ideas = air.fetch_ideas_pending_qa(target_idea_status, limit=limit)
    print(f"[gen-fetch] target ideas: {len(ideas)}", file=sys.stderr)

    payload: dict[str, Any] = {"ideas": []}
    for idx, idea in enumerate(ideas, start=1):
        idea_id = idea["id"]
        fields = idea["fields"]
        slides_records = air.fetch_slides_for_idea(idea_id)

        total = len(slides_records)
        gen_target = [s for s in slides_records if _slide_needs_description(s["fields"])]

        print(
            f"[gen-fetch] {idx}/{len(ideas)} {idea_id} "
            f"gen_target={len(gen_target)}/{total}",
            file=sys.stderr,
        )
        if not gen_target:
            print(f"[gen-fetch] skip {idea_id} (生成待ち+未記入スライド0件)", file=sys.stderr)
            continue

        all_slides: list[dict[str, Any]] = []
        for s in slides_records:
            sf = s["fields"]
            all_slides.append(
                {
                    "slide_id": s["id"],
                    "slide_number": sf.get("slide_number", 0),
                    "label": sf.get("label", ""),
                    "slide_title": sf.get("slide_title", "") or "",
                    "image_description": sf.get("image_description", "") or "",
                    "status": sf.get("status", ""),
                    "needs_description": _slide_needs_description(sf),
                }
            )

        payload["ideas"].append(
            {
                "idea_id": idea_id,
                "title": fields.get("title", ""),
                "overview": fields.get("overview", ""),
                "caption": fields.get("caption", ""),
                "hashtags": fields.get("hashtags", ""),
                "slides": all_slides,
            }
        )

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch image-description-pending ideas")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("/tmp/gen_pending.json"))
    args = parser.parse_args()
    target_status = os.environ.get("QA_TARGET_STATUS", "画像生成中")

    payload = build_gen_pending_payload(
        limit=args.limit,
        target_idea_status=target_status,
    )
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"[gen-fetch] wrote {len(payload['ideas'])} ideas to {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
