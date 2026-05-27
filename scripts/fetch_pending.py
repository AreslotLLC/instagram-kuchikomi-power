"""投稿待ち idea を Airtable から取得し、画像を一時保存して JSON で吐き出す。

Routine 内で実行され、後続の Claude Code セッション本体が
この JSON と画像ファイルを Read してサブエージェントに渡す。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from scripts.airtable_client import KuchikomiAirtable  # noqa: E402


def _download_image(url: str, dst: Path) -> Path:
    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dst.write_bytes(resp.content)
    return dst


SLIDE_TARGET_STATUS = "投稿待ち"


def _slide_is_qa_target(sfields: dict[str, Any]) -> bool:
    if sfields.get("status", "") != SLIDE_TARGET_STATUS:
        return False
    slide_qa_status = sfields.get("slide_qa_status", "")
    return slide_qa_status in ("", "未検査", "FAIL")


def _slide_was_regenerated_after_qa(sfields: dict[str, Any]) -> bool:
    """FAIL スライドが最後の QA 検査より後に再生成されたか判定する。"""
    if sfields.get("slide_qa_status") != "FAIL":
        return False
    slide_qa_checked_at_str = sfields.get("slide_qa_checked_at")
    if not slide_qa_checked_at_str:
        return False
    generated_at_str = sfields.get("generated_at")
    if not generated_at_str:
        return False
    try:
        return _parse_dt(generated_at_str) > _parse_dt(slide_qa_checked_at_str)
    except (ValueError, TypeError):
        return False


def _parse_dt(s: str) -> datetime:
    """ISO 8601 文字列を timezone-aware datetime に変換する。Z suffix も許容。"""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _idea_has_regenerated_slides(
    idea_fields: dict[str, Any], slides_records: list[dict[str, Any]]
) -> bool:
    """FAIL ideaについて、最後のQA検査より後に再生成されたスライドが1枚でもあるか判定する。
    qa_status が FAIL 以外の idea は常に True を返す。
    qa_checked_at が未設定（初回）の場合も True を返す。"""
    if idea_fields.get("qa_status") != "FAIL":
        return True

    qa_checked_at_str = idea_fields.get("qa_checked_at")
    if not qa_checked_at_str:
        return True  # QA未実施扱い

    try:
        qa_checked_dt = _parse_dt(qa_checked_at_str)
    except (ValueError, TypeError):
        return True  # パース失敗時は安全側（対象に含める）

    for s in slides_records:
        generated_at_str = s["fields"].get("generated_at")
        if generated_at_str:
            try:
                if _parse_dt(generated_at_str) > qa_checked_dt:
                    return True
            except (ValueError, TypeError):
                pass

    return False


def build_pending_payload(
    *,
    limit: int | None,
    image_dir: Path,
    target_status: str,
) -> dict[str, Any]:
    air = KuchikomiAirtable()
    ideas = air.fetch_ideas_pending_qa(target_status, limit=limit)
    print(f"[fetch] target ideas: {len(ideas)}", file=sys.stderr)
    image_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {"ideas": []}
    for idx, idea in enumerate(ideas, start=1):
        idea_id = idea["id"]
        fields = idea["fields"]
        slides_records = air.fetch_slides_for_idea(idea_id)

        if not _idea_has_regenerated_slides(fields, slides_records):
            print(
                f"[fetch] skip {idea_id} (FAIL後に再生成なし)",
                file=sys.stderr,
            )
            continue

        total_slides = len(slides_records)
        slides: list[dict[str, Any]] = []
        skipped_slides = 0
        for s in slides_records:
            sid = s["id"]
            sfields = s["fields"]
            if not _slide_is_qa_target(sfields):
                skipped_slides += 1
                continue
            if _slide_was_regenerated_after_qa(sfields):
                try:
                    air.reset_slide_qa_status(sid)
                except Exception as exc:  # noqa: BLE001
                    print(f"[fetch][warn] reset slide_qa_status fail {sid}: {exc}", file=sys.stderr)
            url = sfields.get("generated_image_url", "")
            local_path: str | None = None
            if url:
                try:
                    local_path = str(
                        _download_image(url, image_dir / f"{idea_id}__{sid}.png")
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[fetch][warn] download fail {sid}: {exc}", file=sys.stderr)
            slides.append(
                {
                    "slide_id": sid,
                    "slide_number": sfields.get("slide_number", 0),
                    "slide_title": sfields.get("slide_title", ""),
                    "image_description": sfields.get("image_description", ""),
                    "generated_image_url": url,
                    "local_image_path": local_path,
                    "status": sfields.get("status", ""),
                    "slide_qa_status": sfields.get("slide_qa_status", ""),
                }
            )
        print(
            f"[fetch] {idx}/{len(ideas)} {idea_id} "
            f"slides={len(slides)}/{total_slides} skipped={skipped_slides}",
            file=sys.stderr,
        )
        if not slides:
            print(f"[fetch] skip {idea_id} (QA対象スライド0件)", file=sys.stderr)
            continue
        payload["ideas"].append(
            {
                "idea_id": idea_id,
                "title": fields.get("title", ""),
                "overview": fields.get("overview", ""),
                "caption": fields.get("caption", ""),
                "hashtags": fields.get("hashtags", ""),
                "qa_attempt_no_prev": int(fields.get("qa_attempt_no", 0) or 0),
                "slides": slides,
            }
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch pending Instagram QA ideas")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("/tmp/qa_pending.json"))
    parser.add_argument("--image-dir", type=Path, default=Path("/tmp/qa_images"))
    args = parser.parse_args()
    target_status = os.environ.get("QA_TARGET_STATUS", "投稿待ち")

    payload = build_pending_payload(
        limit=args.limit,
        image_dir=args.image_dir,
        target_status=target_status,
    )
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[fetch] wrote {len(payload['ideas'])} ideas to {args.output} "
        f"(images in {args.image_dir})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
