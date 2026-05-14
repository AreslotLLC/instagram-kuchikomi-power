# Instagram 口コミパワー — 投稿前 QA サブエージェント

Instagram「口コミパワー」アカウントの**カルーセル投稿(5枚)**を、投稿前に Claude Vision で検査するサブエージェント実装。
PDF「サブエージェント設計テンプレート」の `thumb-qa` + `video-qa` を Instagram 静止画用に統合した1体構成。

## 構成

```
.claude/
  agents/
    instagram-image-qa.md    # サブエージェント定義 (PDF標準フォーマット)
scripts/
  qa_runner.py               # オーケストレーター
  airtable_client.py         # Airtable I/O
  vision_qa.py               # Claude Vision 呼び出し
  discord_notifier.py        # Discord Webhook 通知
```

オーケストレーター(`qa_runner.py`)は PDF原則4「オーケストレーターはあなた(Claudeセッション本体)」の役割を、Python から再現したものです。
`scripts/vision_qa.py` は `.claude/agents/instagram-image-qa.md` の本文をシステムプロンプトとして読み込むため、サブエージェント定義と API 実装が一致します。

## 前提

- Airtable Base `appkaalWhOFGQ7qYX`(口コミパワー本番)に下記 QA フィールド追加済み:
  - `Instagram_contents_ideas`: `qa_status`, `qa_score`, `qa_findings`, `qa_checked_at`, `qa_attempt_no`
  - `Instagram_slides`: `slide_qa_status`, `slide_qa_score`, `slide_qa_findings`, `slide_qa_checked_at`

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env を編集して各シークレットを設定
```

必要な環境変数:

| 変数 | 説明 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー |
| `ANTHROPIC_MODEL` | 既定 `claude-opus-4-7` |
| `AIRTABLE_PAT` | Airtable Personal Access Token |
| `AIRTABLE_BASE_ID` | `appkaalWhOFGQ7qYX` |
| `AIRTABLE_TABLE_IDEAS` | `tbl7k3PRdVHPFCUYR` |
| `AIRTABLE_TABLE_SLIDES` | `tbltCQz4IfEydvXmR` |
| `DISCORD_WEBHOOK_URL` | Discord通知先(空ならスキップ) |
| `QA_PASS_THRESHOLD` | PASS とみなす総合スコア (既定 80) |
| `QA_MAX_ATTEMPTS` | これを超えたFAILは「要承認」に格上げ (既定 3) |
| `QA_TARGET_STATUS` | 対象 `status` (既定 `投稿待ち`) |

## 使い方

```bash
# Airtable取得とpayload組み立てだけ確認
python -m scripts.qa_runner --dry-run --limit 1

# 1件だけ本番QA
python -m scripts.qa_runner --limit 1

# 投稿待ちの未QA を全件処理
python -m scripts.qa_runner
```

`qa_status='投稿待ち'` かつ `qa_status` が 空 / `未検査` / `FAIL` のレコードを `投稿順` 昇順で処理し、各 idea ごとに:

1. `qa_status` を `検査中` に更新
2. 5枚の `generated_image_url` を Claude Vision に渡して採点
3. 結果に応じて `PASS` / `FAIL` / `要承認` に更新、各スライドの `slide_qa_*` も更新
4. Discord に1件ずつ embed 通知 + バッチ完了時にサマリー通知

`QA_MAX_ATTEMPTS` を超えても FAIL なら自動で `要承認` に格上げ(人の判断待ち)。

## Make シナリオの改修(次工程、本リポでは未実装)

既存の `【口コミパワー】Instagram自動投稿` (5407258) は、先頭フィルタを次のように1行追加するだけで連携完了:

```
AND({status}='投稿待ち', OR({qa_status}='PASS', {qa_status}='要承認'))
```

これで「QA未通過 / FAIL」は投稿対象から外れます。

## サブエージェント定義の更新

`.claude/agents/instagram-image-qa.md` を編集すると、次回 `qa_runner.py` 実行から自動で反映されます(YAMLフロントマターは無視され、Markdown本体がシステムプロンプトに使われる)。
