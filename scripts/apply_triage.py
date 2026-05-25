"""FAIL スライドのトリアージ結果を Airtable に反映する。

入力 JSON フォーマット:
{
  "results": [
    {
      "idea_id": "recXXXX",
      "slides": [
        {
          "slide_id": "recYYYY",
          "triage_action": "再生成" | "プロンプト変更",
          "triage_reason": "判断理由",
          "new_image_description": "..."   // プロンプト変更の場合のみ
        }
      ]
    }
  ]
}

triage_action ごとの処理:
  "再生成"          → status=再生成待ち, slide_qa_status=未検査
  "プロンプト変更"  → image_description を更新してから status=再生成待ち, slide_qa_status=未検査
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from scripts.airtable_client import KuchikomiAirtable  # noqa: E402


def apply_triage(input_path: Path) -> int:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    results = data.get("results", [])

    air = KuchikomiAirtable()
    counts: dict[str, int] = {"再生成": 0, "プロンプト変更": 0, "error": 0}

    for idea_result in results:
        idea_id = idea_result.get("idea_id", "?")
        for slide in idea_result.get("slides", []):
            slide_id = slide.get("slide_id", "?")
            action = slide.get("triage_action", "再生成")
            try:
                fields: dict = {"status": "再生成待ち", "slide_qa_status": "未検査"}
                if action == "プロンプト変更":
                    new_desc = slide.get("new_image_description", "")
                    if new_desc:
                        fields["image_description"] = new_desc
                    counts["プロンプト変更"] += 1
                else:
                    counts["再生成"] += 1
                air._slides.update(slide_id, fields)
                print(
                    f"[triage] {slide_id} idea={idea_id} [{action}] → 再生成待ち/未検査",
                    file=sys.stderr,
                )
            except Exception:  # noqa: BLE001
                counts["error"] += 1
                traceback.print_exc()

    print(
        f"[triage][done] 再生成={counts['再生成']} プロンプト変更={counts['プロンプト変更']} errors={counts['error']}",
        file=sys.stderr,
    )
    return 0 if counts["error"] == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply triage results to Airtable")
    parser.add_argument("--input", type=Path, default=Path("/tmp/qa_triage.json"))
    args = parser.parse_args()
    sys.exit(apply_triage(args.input))


if __name__ == "__main__":
    main()
