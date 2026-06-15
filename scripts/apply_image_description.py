"""image_description 生成結果を Airtable の Instagram_slides に書き戻す。

入力: /tmp/gen_results.json
  {"results": [{"idea_id": "...", "slides": [{"slide_id": "...", "slide_title": "...", "image_description": "..."}]}]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from scripts.airtable_client import KuchikomiAirtable  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("/tmp/gen_results.json"))
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    results = data.get("results", [])

    air = KuchikomiAirtable()
    total_slides = 0
    errors = 0

    for result in results:
        idea_id = result.get("idea_id", "?")
        for slide in result.get("slides", []):
            slide_id = slide.get("slide_id", "")
            slide_title = slide.get("slide_title", "") or ""
            image_description = slide.get("image_description", "") or ""

            if not slide_id or not image_description.strip():
                print(
                    f"[apply-desc] skip {slide_id} (image_description が空)",
                    file=sys.stderr,
                )
                continue
            try:
                air.update_slide_description(
                    slide_id,
                    slide_title=slide_title,
                    image_description=image_description,
                )
                print(
                    f"[apply-desc] updated {slide_id} (idea={idea_id})",
                    file=sys.stderr,
                )
                total_slides += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[apply-desc][error] {slide_id}: {exc}", file=sys.stderr)
                errors += 1

    print(
        f"[apply-desc][done] slides={total_slides} errors={errors}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
