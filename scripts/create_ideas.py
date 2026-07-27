"""新規の投稿企画（idea + 5スライド）を Airtable に登録する。

入力 JSON は企画の中身だけを持ち、ステータス遷移や既定値はこのスクリプトが決める。

    {"ideas": [
      {"title": "...", "category": "ハウツー型", "topic": "口コミ対策",
       "target_audience": ["飲食店"], "hook_type": "損失回避",
       "overview": "...", "caption": "...", "hashtags": "#a #b", "sources": "...",
       "post_order": 106, "post_date": "2026-07-28", "post_time": "11:00",
       "slides": [{"slide_number": 1, "label": "...（表紙）"}, ...]}
    ]}

作成される idea は status="画像生成中" / qa_status="未検査"、
スライドは status="生成待ち" かつ image_description 未記入で作られる。
この状態が image-description-gen → 画像生成シナリオ → QAゲート の入口になる。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from scripts.airtable_client import KuchikomiAirtable  # noqa: E402


IDEA_INIT_STATUS = "画像生成中"
IDEA_INIT_QA_STATUS = "未検査"
SLIDE_INIT_STATUS = "生成待ち"

REQUIRED = (
    "title",
    "category",
    "topic",
    "target_audience",
    "hook_type",
    "overview",
    "caption",
    "hashtags",
    "post_order",
    "post_date",
    "slides",
)


def _validate(idea: dict[str, Any], index: int) -> list[str]:
    errors = []
    for key in REQUIRED:
        if not idea.get(key):
            errors.append(f"ideas[{index}]: {key} が空")
    slides = idea.get("slides") or []
    if slides and len(slides) != 5:
        errors.append(f"ideas[{index}]: スライドが{len(slides)}枚（5枚必要）")
    numbers = sorted(s.get("slide_number") for s in slides)
    if slides and numbers != [1, 2, 3, 4, 5]:
        errors.append(f"ideas[{index}]: slide_number が 1..5 でない: {numbers}")
    for s in slides:
        if not str(s.get("label", "")).strip():
            errors.append(f"ideas[{index}]: slide {s.get('slide_number')} の label が空")
    return errors


def _idea_fields(idea: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "title": idea["title"],
        "category": idea["category"],
        "topic": idea["topic"],
        "target_audience": idea["target_audience"],
        "hook_type": idea["hook_type"],
        "overview": idea["overview"],
        "caption": idea["caption"],
        "hashtags": idea["hashtags"],
        "投稿順": idea["post_order"],
        "投稿予定日": idea["post_date"],
        "status": IDEA_INIT_STATUS,
        "qa_status": IDEA_INIT_QA_STATUS,
    }
    if idea.get("post_time"):
        fields["投稿時刻"] = idea["post_time"]
    if idea.get("sources"):
        fields["sources"] = idea["sources"]
    return fields


def main() -> None:
    parser = argparse.ArgumentParser(description="Create new Instagram content ideas")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Airtable に書き込まず、検証と件数の確認だけ行う",
    )
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    ideas = payload.get("ideas", [])

    errors: list[str] = []
    for i, idea in enumerate(ideas):
        errors.extend(_validate(idea, i))
    if errors:
        for e in errors:
            print(f"[create][error] {e}", file=sys.stderr)
        print(f"[create][done] 中断: 入力エラー {len(errors)}件", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        for idea in ideas:
            print(
                f"[create][dry] 投稿順{idea['post_order']} {idea['post_date']} "
                f"{idea['category']}/{idea['topic']} {idea['title']}",
                file=sys.stderr,
            )
        print(
            f"[create][done] dry-run: idea {len(ideas)}件 / "
            f"slide {sum(len(i['slides']) for i in ideas)}件 (書き込みなし)",
            file=sys.stderr,
        )
        return

    air = KuchikomiAirtable()
    created_ideas = 0
    created_slides = 0
    failed: list[str] = []

    for idea in ideas:
        title = idea["title"]
        try:
            idea_id = air.create_idea(_idea_fields(idea))
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{title}: idea作成失敗 {exc}")
            print(f"[create][error] {title}: {exc}", file=sys.stderr)
            continue
        created_ideas += 1
        try:
            slide_ids = air.create_slides(idea_id, idea["slides"])
            created_slides += len(slide_ids)
        except Exception as exc:  # noqa: BLE001
            failed.append(f"{title}: slide作成失敗 {exc}")
            print(f"[create][error] {title} slides: {exc}", file=sys.stderr)
            continue
        print(
            f"[create] 投稿順{idea['post_order']} {idea['post_date']} "
            f"{idea_id} slides={len(slide_ids)} {title}",
            file=sys.stderr,
        )

    print(
        f"[create][done] idea {created_ideas}/{len(ideas)}件 / "
        f"slide {created_slides}件 / 失敗 {len(failed)}件",
        file=sys.stderr,
    )
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
