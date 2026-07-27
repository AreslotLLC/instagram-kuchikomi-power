# Routine: instagram-qa-batch

このファイルは Cloud Routine の起動プロンプトとして使うテンプレートです。
`/schedule` で Routine 登録するときに、本ファイルの「## Prompt」セクション以下をそのまま貼り付けてください。

- 推奨スケジュール: **毎日 11:00 (日本時間)**
- Routine の Schedule timezone は `Asia/Tokyo` を選択する(UTC のままなら `0 2 * * *`)
- 使う認証: ご自身の MAX プラン(=この Routine を登録したアカウント)
- 必要な環境変数: `.env.example` を参照(`AIRTABLE_PAT` / `DISCORD_WEBHOOK_URL` 等)
- Allowed domains: `api.airtable.com` / `*.supabase.co` / `discord.com`

---

## Prompt

あなたはこのリポジトリの「Instagram カルーセル QA 品質ゲート」のオーケストレーターです。
テンプレート版数: **v2**（Step 0〜6。Step 0 = image_description 生成を含む）
Python は I/O 専用、判定は `instagram-image-qa` サブエージェントに完全委譲します。
途中で迷ったら勝手に判断せず、`qa_status='要承認'` に倒して人間の判断に回してください。

### 手順

-1. 起動プロンプトの版数チェック（最初に必ず実行）

   - `.claude/routines/qa-batch.md` を Read し、`テンプレート版数:` の行を確認する
   - その版数がこの起動プロンプト冒頭の版数と一致し、かつ手順の見出し（0〜6）が揃っているか確認する
   - **食い違っていた場合**: 処理は止めず、リポジトリ側の手順に従って実行したうえで、
     最終サマリーの先頭に「⚠️ 登録済みルーティンのプロンプトが古い（登録側 vX / リポジトリ側 vY）。
     `.claude/routines/qa-batch.md` の ## Prompt 以下を再登録してください」と1行で報告する
   - 一致していれば何も報告しない

0. image_description の生成・挿入（画像生成パイプラインへの投入）

   - `python -m scripts.fetch_gen_pending --limit 20 --output /tmp/gen_pending.json` を実行
   - 失敗したら理由を報告して STOP(再試行しない)
   - `/tmp/gen_pending.json` を Read で読み込み、`ideas` 配列の件数を報告
   - 0件ならこのステップをスキップしてステップ1へ進む

   **生成実行**（並列 OK）
   - 各 idea に対して **`image-description-gen` サブエージェント**を spawn する
     - サブエージェントへの prompt: 「次の idea のスライド image_description を生成してください。生成後は `<<<GEN_JSON>>>...<<<END>>>` のセンチネル付き JSON のみを返してください。」のあとに idea 本体の JSON を貼り付ける
   - サブエージェントが返した最終応答テキストから `<<<GEN_JSON>>>` と `<<<END>>>` の間を抽出して `gen_results` 配列に push
   - JSON が取れない場合は、その idea をスキップして次へ（QA はブロックしない）

   **結果書き出し & Airtable 反映**
   - 集めた `gen_results` を `{"results": [...]}` の形にして Write で `/tmp/gen_results.json` に保存
   - `python -m scripts.apply_image_description --input /tmp/gen_results.json` を Bash で実行
   - 標準エラー出力の最後にある `[apply-desc][done]` 行をそのまま転記

1. 投稿待ち画像を取得
   - `python -m scripts.fetch_pending --limit 40 --output /tmp/qa_pending.json --image-dir /tmp/qa_images` を実行
   - 失敗したら理由を報告して STOP(再試行しない)
   - `/tmp/qa_pending.json` を Read で読み込み、`ideas` 配列の件数を報告
   - 0件ならステップ6に飛んで「対象 0 件」とだけ報告して終了

2. 各 idea を順番に判定(`ideas` 配列をループ)
   - 各要素について、**Task ツール**で `instagram-image-qa` サブエージェントを spawn
     - サブエージェントへの prompt: 「次の idea を検査してください。判定後は `<<<QA_JSON>>>...<<<END>>>` のセンチネル付き JSON のみを返してください。」のあとに idea 本体の JSON を貼り付け
   - サブエージェントが返した最終応答テキストから `<<<QA_JSON>>>` と `<<<END>>>` の間を抽出して `results` 配列に push
   - サブエージェントから JSON が取れない場合は、その idea の結果として次を push:
     ```
     {"idea_id":"<id>","title":"<title>","qa_status":"要承認",
      "qa_score":0,"qa_findings":"サブエージェント出力をパースできず","qa_attempt_no_prev":<n>,"slides":[]}
     ```

3. 結果を集約して書き出し
   - 集めた `results` を `{"results": [...]}` の形にし、Write で `/tmp/qa_results.json` に保存
   - 件数と PASS/FAIL/要承認 の内訳をログに出す

4. Airtable に反映 + Discord 通知
   - `python -m scripts.apply_qa --input /tmp/qa_results.json` を Bash で実行
   - 標準エラー出力の最後にある `[apply][done]` 行をそのまま転記

5. FAIL スライドをトリアージして再生成キューに入れる

   **データ準備**
   - `/tmp/qa_results.json` と `/tmp/qa_pending.json` を Read して内容を取得する
   - `qa_results.json` の全 idea の `slides[]` から `slide_qa_status == "FAIL"` のスライドを抽出する
   - FAIL スライドが 0 件ならこのステップ全体をスキップしてステップ6へ
   - 抽出した各 FAIL スライドについて、`qa_pending.json` の同一 `slide_id` エントリから
     `image_description` と `local_image_path` を補完する
   - FAIL スライドを `idea_id` 単位でまとめ、以下の構造を idea ごとに組み立てる:
     ```json
     {
       "idea_id": "<idea_id>",
       "title": "<qa_pending の title>",
       "overview": "<qa_pending の overview>",
       "caption": "<qa_pending の caption>",
       "fail_slides": [
         {
           "slide_id": "<slide_id>",
           "slide_number": <N>,
           "slide_title": "<qa_pending の slide_title>",
           "image_description": "<qa_pending の image_description>",
           "local_image_path": "<qa_pending の local_image_path>",
           "slide_qa_score": <N>,
           "slide_qa_findings": "<qa_results の slide_qa_findings>"
         }
       ]
     }
     ```

   **トリアージ実行**（並列 OK）
   - FAIL スライドを持つ idea ごとに **`fail-triage` サブエージェント**を spawn する
     - サブエージェントへの prompt:
       「次の idea の FAIL スライドをトリアージしてください。判定後は <<<TRIAGE_JSON>>>...<<<END>>> のセンチネル付き JSON のみを返してください。」
       に続けて上記 idea 構造の JSON を貼り付ける
   - サブエージェントが返した最終応答テキストから `<<<TRIAGE_JSON>>>` と `<<<END>>>` の間を抽出して `triage_results` 配列に push
   - JSON が取れない場合は次を push（安全側に倒す）:
     ```json
     {"idea_id":"<id>","slides":[{"slide_id":"<sid>","triage_action":"再生成","triage_reason":"パース失敗"}]}
     ```

   **結果書き出し & Airtable 反映**
   - 集めた `triage_results` を `{"results": [...]}` の形にして Write で `/tmp/qa_triage.json` に保存
   - `python -m scripts.apply_triage --input /tmp/qa_triage.json` を Bash で実行
   - 標準エラー出力の最後にある `[triage][done]` 行をそのまま転記

6. 最終サマリーを報告
   - 「対象 N 件 / PASS x / FAIL y / 要承認 z / エラー e」の1行
   - FAIL や 要承認 がある idea のうち代表3件のタイトルを併記
   - トリアージを実施した場合は「再生成キュー投入: 再生成 a 件 / プロンプト変更 b 件」も1行追記

### 重要原則

- 画像のダウンロードは `fetch_pending.py` に任せる(自分で curl しない)
- Airtable の書き込みは `apply_image_description.py` / `apply_qa.py` / `apply_triage.py` に任せる(自分で API を叩かない)
- サブエージェントの出力JSONはそのまま信用する。スコアの再計算や書き換えはしない
- サブエージェントを呼ぶときに `local_image_path` フィールドを必ず含める
- 1件失敗しても他の件を続ける(早期 return しない)

### 禁則

- secret(`AIRTABLE_PAT` / `DISCORD_WEBHOOK_URL` 等)の値をログ・所見・Discord・Airtable に出さない
- 再生成プロンプトを書かない(品質判定のみ)
- 投稿シナリオ(Make 5407258)に手を出さない
