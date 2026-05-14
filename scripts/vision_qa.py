from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from anthropic import Anthropic


AGENT_DEFINITION_PATH = Path(__file__).resolve().parent.parent / ".claude" / "agents" / "instagram-image-qa.md"

SENTINEL_OPEN = "<<<QA_JSON>>>"
SENTINEL_CLOSE = "<<<END>>>"


def _load_agent_system_prompt() -> str:
    raw = AGENT_DEFINITION_PATH.read_text(encoding="utf-8")
    # Strip the leading YAML frontmatter so the agent definition itself becomes
    # the system prompt body. The harness fields (name/description/tools) are
    # not useful to the API call.
    body = re.sub(r"^---\n.*?\n---\n", "", raw, count=1, flags=re.DOTALL)
    return body.strip()


def _download_image_as_block(url: str) -> dict[str, Any]:
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        media_type = resp.headers.get("content-type", "image/png").split(";")[0].strip()
        data_b64 = base64.standard_b64encode(resp.content).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data_b64,
        },
    }


def _extract_json(text: str) -> dict[str, Any]:
    start = text.find(SENTINEL_OPEN)
    end = text.find(SENTINEL_CLOSE)
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"sentinel not found in response: {text[:500]}")
    payload = text[start + len(SENTINEL_OPEN) : end].strip()
    payload = payload.lstrip("`").rstrip("`")
    if payload.startswith("json"):
        payload = payload[4:].strip()
    return json.loads(payload)


class VisionQA:
    def __init__(self) -> None:
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
        self._system = _load_agent_system_prompt()

    def evaluate_idea(self, idea_payload: dict[str, Any]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "次のJSONは、これから検査する1投稿(カルーセル)の入力データです。\n"
                    "このあとに添付する画像群は、slide_numberの昇順で並んでいます。\n"
                    "サブエージェント定義に従い、各スライドと全体を検査し、"
                    f"{SENTINEL_OPEN} と {SENTINEL_CLOSE} で挟んだJSONのみを出力してください。\n\n"
                    f"```json\n{json.dumps(idea_payload, ensure_ascii=False, indent=2)}\n```"
                ),
            }
        ]
        for slide in idea_payload["slides"]:
            url = slide.get("generated_image_url")
            label = f"slide_number={slide['slide_number']} / slide_id={slide['slide_id']}"
            if not url:
                content.append({"type": "text", "text": f"[{label}] 画像URLなし(未生成)"})
                continue
            try:
                content.append({"type": "text", "text": f"[{label}]"})
                content.append(_download_image_as_block(url))
            except Exception as exc:  # noqa: BLE001
                content.append(
                    {"type": "text", "text": f"[{label}] 画像取得失敗: {exc}"}
                )

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._system,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return _extract_json(text)
