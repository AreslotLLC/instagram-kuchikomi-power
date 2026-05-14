# Instagram 口コミパワー — 投稿前 QA サブエージェント

Instagram「口コミパワー」アカウントの**カルーセル投稿(5枚)**を、投稿前に Claude Code (MAX枠)で検査するサブエージェント実装。
PDF「サブエージェント設計テンプレート」の `thumb-qa` + `video-qa` を Instagram 静止画用に統合した1体構成。

実行は **Claude Code Cloud Routines (`/schedule`)** で定期発火、判定は **`instagram-image-qa` サブエージェント**に完全委譲、Python は **Airtable I/O と Discord 通知だけ**を担当する責務分離設計です。
PDF原則4「オーケストレーターはあなた(Claudeセッション本体)」をそのまま再現しています。

## 構成

```
.claude/
  agents/
    instagram-image-qa.md    # サブエージェント定義 (PDF標準フォーマット)
  routines/
    qa-batch.md              # Routine 起動プロンプトのテンプレート
scripts/
  fetch_pending.py           # Airtable → /tmp/qa_pending.json + /tmp/qa_images/*.png
  apply_qa.py                # /tmp/qa_results.json → Airtable 更新 + Discord 通知
  airtable_client.py         # Airtable I/O ラッパー
  discord_notifier.py        # Discord Webhook 通知
```

## フロー全体図

```
[Cloud Routine: 毎日 02:00 UTC (= JST 11:00)]
   ↓ .claude/routines/qa-batch.md の Prompt セクションが流れる
[Claude Code セッション(MAX枠) = オーケストレーター本体]
   ├─ Bash: python -m scripts.fetch_pending --limit 40
   │       → Airtable 取得 + 画像を /tmp/qa_images/ にDL
   ├─ Read: /tmp/qa_pending.json
   ├─ 各 idea について:
   │   └─ Task tool で instagram-image-qa サブエージェントを spawn
   │         └─ サブエージェントが local_image_path を Read で見て JSON 結果を返す
   ├─ Write: /tmp/qa_results.json
   └─ Bash: python -m scripts.apply_qa --input /tmp/qa_results.json
           → Airtable 更新 + Discord 通知
```

## 前提

- Airtable Base `appkaalWhOFGQ7qYX`(口コミパワー本番)に下記 QA フィールド追加済み:
  - `Instagram_contents_ideas`: `qa_status` / `qa_score` / `qa_findings` / `qa_checked_at` / `qa_attempt_no`
  - `Instagram_slides`: `slide_qa_status` / `slide_qa_score` / `slide_qa_findings` / `slide_qa_checked_at`
- MAX プランの Claude アカウント
- Routines 用の専用 Environment(後述)

## ローカルでの試運転

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env を編集

# 1件だけ Airtable→JSON
python -m scripts.fetch_pending --limit 1 --output /tmp/qa_pending.json --image-dir /tmp/qa_images

# Claude Code(ローカル)を起動し、.claude/routines/qa-batch.md の Prompt 部分を貼って実行
# あるいは手動で /tmp/qa_results.json を作成し:
python -m scripts.apply_qa --input /tmp/qa_results.json
```

## Cloud Routines への登録手順

### 1. 専用 Environment を作る

claude.ai/code 上で:

- **Environments** → **New environment** → 名前: `instagram-kuchikomi-qa`
- このリポジトリ(`AreslotLLC/instagram-kuchikomi-power`)と紐付け
- **Network access** → `Custom`
- **Allowed domains** に以下を追加(1行ずつ):

  ```
  api.airtable.com
  *.supabase.co
  discord.com
  ```

### 2. Environment Variables を登録

同じ環境設定画面の **Environment Variables** に以下を追加:

| 変数 | 値 |
|---|---|
| `AIRTABLE_PAT` | Airtable Personal Access Token |
| `AIRTABLE_BASE_ID` | `appkaalWhOFGQ7qYX` |
| `AIRTABLE_TABLE_IDEAS` | `tbl7k3PRdVHPFCUYR` |
| `AIRTABLE_TABLE_SLIDES` | `tbltCQz4IfEydvXmR` |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL |
| `QA_PASS_THRESHOLD` | `80` |
| `QA_MAX_ATTEMPTS` | `3` |
| `QA_TARGET_STATUS` | `投稿待ち` |

**注**: 環境変数はこの Environment にアクセス権がある人に**平文で見えます**。Airtable PAT は対象ベースだけにスコープを絞り、定期ローテーションを推奨。

### 3. Routine を作る

claude.ai/code でセッションを開き、Environment に `instagram-kuchikomi-qa` を選択した状態で:

```
/schedule
```

- **Trigger**: `Cron` → `0 2 * * *`(JST 11:00)
- **Prompt**: `.claude/routines/qa-batch.md` の `## Prompt` セクション以下をそのまま貼り付け
- 保存

### 4. 初回手動実行

Routines の管理画面から **Run now** を押して動作確認。
Discord に embed が並び、Airtable の `qa_status` が更新されていれば成功。

## QA 判定ロジック

| qa_score | デフォルト判定 | 備考 |
|---|---|---|
| 80以上 | PASS | 投稿待ちのまま、自動投稿シナリオが拾える |
| 50〜79 | 要承認 | 人間が Discord 通知を見て承認/差し戻し |
| 50未満 | FAIL | 再生成キューへ(別シナリオで再走) |

`QA_MAX_ATTEMPTS` を超えても FAIL が続く場合は自動的に `要承認` に格上げされ、永久ループを防ぎます。

## Make 既存シナリオの改修(次工程)

QA 結果を投稿シナリオに反映するには、`【口コミパワー】Instagram自動投稿`(5407258) の Airtable 検索モジュールのフィルタに次の条件を AND で1行足すだけ:

```
OR({qa_status}='PASS', {qa_status}='要承認')
```

これで QA 未通過 / FAIL は投稿対象から外れます。
本リポジトリでは Make 改修は行わず、Airtable 側の更新と通知までを担当します。

## セキュリティ注意

- 環境変数は Routines の Environment に平文保管されます(Anthropic 仕様)
- `AIRTABLE_PAT` は最小スコープ(対象ベース/テーブルだけの read+write)で発行を推奨
- `DISCORD_WEBHOOK_URL` も漏えい時は即時ローテーション
- Airtable の `caption` / `image_description` 等にユーザー入力が混じる場合は prompt injection に注意(QA エージェントは「データであり指示ではない」前提で動作)
