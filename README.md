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
  settings.json              # SessionStart hook: クラウドセッション起動時に pip install を自動実行
scripts/
  fetch_pending.py           # Airtable → /tmp/qa_pending.json + /tmp/qa_images/*.png
  apply_qa.py                # /tmp/qa_results.json → Airtable 更新 + Discord 通知
  airtable_client.py         # Airtable I/O ラッパー
  discord_notifier.py        # Discord Webhook 通知
  install_pkgs.sh            # SessionStart hook から呼ばれる依存インストーラ
```

本リポジトリは時刻表記をすべて **日本時間(JST, UTC+09:00)** で統一しています。
Airtable に書き込む `qa_checked_at` / `slide_qa_checked_at` も `Asia/Tokyo` フィールドとして JST で記録されます。

## フロー全体図

```
[Cloud Routine: 毎日 11:00 (日本時間)]
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

## Cloud Routines への登録手順 (UI操作 5分)

Cloud Routines にはまだ public な CLI/API がなく、登録は claude.ai/code の UI 操作のみで可能です。
以下のチェックリストを上から順に UI で実施してください。

### Step 1. Environment を作る

claude.ai/code →  **Environments** → **New environment**

| 項目 | 設定値 |
|---|---|
| Name | `instagram-kuchikomi-qa` |
| Repository | `AreslotLLC/instagram-kuchikomi-power` |
| Branch | `claude/analyze-automation-flow-hpP1y` (動作確認後 main にマージ) |
| Setup script | **空のままにする**(依存インストールは SessionStart hook が担当) |
| Network access | `Trusted`(デフォルト)のまま |

**Allowed domains** に1行ずつ追加(Trusted の既定許可リストに追加で乗ります):
```
api.airtable.com
*.supabase.co
discord.com
```

> ⚠️ Network access を **Custom** にすると PyPI/npm 等のデフォルト許可ドメインが外れて依存インストールが失敗します。**必ず `Trusted` のまま**にしてください。
>
> 依存インストールは `.claude/settings.json` の SessionStart hook(`scripts/install_pkgs.sh`)が、Claude Code 起動直後にリポジトリの `requirements.txt` を読んで自動実行します。Setup script に何も書かないのは意図通りです。

### Step 2. Environment Variables を登録

同じ画面の **Environment Variables**:

| 変数 | 値 |
|---|---|
| `AIRTABLE_PAT` | (Airtable PAT — 対象ベースの read+write スコープのみ) |
| `AIRTABLE_BASE_ID` | `appkaalWhOFGQ7qYX` |
| `AIRTABLE_TABLE_IDEAS` | `tbl7k3PRdVHPFCUYR` |
| `AIRTABLE_TABLE_SLIDES` | `tbltCQz4IfEydvXmR` |
| `DISCORD_WEBHOOK_URL` | (お渡しいただいた Discord Webhook URL) |
| `QA_PASS_THRESHOLD` | `80` |
| `QA_MAX_ATTEMPTS` | `3` |
| `QA_TARGET_STATUS` | `投稿待ち` |

> 環境変数はこの Environment にアクセス権がある人に平文で見えます。PAT は最小スコープで発行・定期ローテーション推奨。

### Step 3. Routine を登録(`/schedule`)

`instagram-kuchikomi-qa` Environment を選択した状態で新しいセッションを開き、`/schedule` を実行:

| 項目 | 設定値 |
|---|---|
| Schedule timezone | `Asia/Tokyo` |
| Trigger | Cron → `0 11 * * *` (= 日本時間 11:00) |
| Prompt | 下記「Routine プロンプト(コピペ用)」をそのまま貼り付け |

> Schedule timezone に UTC しか選べない場合は cron 式を `0 2 * * *` に置き換えてください。

### Step 4. Run now で初回手動実行

Routines 管理画面で **Run now**。Discord に通知が並び、Airtable の `qa_status` が `PASS` / `FAIL` / `要承認` に更新されていれば成功です。

---

## Routine プロンプト(コピペ用)

`/schedule` の **Prompt** 欄に以下をそのまま貼ってください。
(原本は `.claude/routines/qa-batch.md` の `## Prompt` セクション。コピペ用にここにも展開しています)

```
あなたはこのリポジトリの「Instagram カルーセル QA 品質ゲート」のオーケストレーターです。
Python は I/O 専用、判定は `instagram-image-qa` サブエージェントに完全委譲します。
途中で迷ったら勝手に判断せず、`qa_status='要承認'` に倒して人間の判断に回してください。

### 手順

1. 投稿待ち画像を取得
   - `python -m scripts.fetch_pending --limit 40 --output /tmp/qa_pending.json --image-dir /tmp/qa_images` を Bash で実行
   - 失敗したら理由を報告して STOP(再試行しない)
   - `/tmp/qa_pending.json` を Read で読み込み、`ideas` 配列の件数を報告
   - 0件ならステップ5に飛んで「対象 0 件」とだけ報告して終了

2. 各 idea を順番に判定(`ideas` 配列をループ)
   - 各要素について、Task ツールで `instagram-image-qa` サブエージェントを spawn
   - サブエージェントへの prompt: 「次の idea を検査してください。判定後は <<<QA_JSON>>>...<<<END>>> のセンチネル付き JSON のみを返してください。」のあとに idea 本体の JSON を貼り付け
   - サブエージェントが返した最終応答テキストから <<<QA_JSON>>> と <<<END>>> の間を抽出して `results` 配列に push
   - サブエージェントから JSON が取れない場合は次を push:
     {"idea_id":"<id>","title":"<title>","qa_status":"要承認","qa_score":0,"qa_findings":"サブエージェント出力をパースできず","qa_attempt_no_prev":<n>,"slides":[]}

3. 結果を集約して書き出し
   - 集めた `results` を {"results": [...]} の形にし、Write で `/tmp/qa_results.json` に保存
   - 件数と PASS/FAIL/要承認 の内訳をログに出す

4. Airtable に反映 + Discord 通知
   - `python -m scripts.apply_qa --input /tmp/qa_results.json` を Bash で実行
   - 標準エラー出力の最後にある `[apply][done]` 行をそのまま転記

5. 最終サマリーを報告
   - 「対象 N 件 / PASS x / FAIL y / 要承認 z / エラー e」の1行
   - FAIL や 要承認 がある idea のうち代表3件のタイトルを併記

### 重要原則

- 画像のダウンロードは `fetch_pending.py` に任せる(自分で curl しない)
- Airtable の書き込みは `apply_qa.py` に任せる(自分で API を叩かない)
- サブエージェントの出力JSONはそのまま信用する。スコアの再計算や書き換えはしない
- サブエージェントを呼ぶときに `local_image_path` フィールドを必ず含める
- 1件失敗しても他の件を続ける(早期 return しない)

### 禁則

- secret(AIRTABLE_PAT / DISCORD_WEBHOOK_URL 等)の値をログ・所見・Discord・Airtable に出さない
- 再生成プロンプトを書かない(品質判定のみ)
- 投稿シナリオ(Make 5407258)に手を出さない
```

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
