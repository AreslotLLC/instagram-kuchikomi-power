# ⚠️ このシステムは停止済み・instagram-engine へ移行中（2026-07-30）

ユーザー決定（2026-07-30）により、口コミパワーのInstagram運用は
**AreslotLLC/instagram-engine**（旧feed-generator・全体設計 `docs/redesign-v2.md` §16）へ統合される。

## 停止状況

- Make シナリオ 5407258「【口コミパワー】Instagram自動投稿」: **無効化済み**（2026-07-30）
- Cloud Routine「【口コミパワー】InstaQA&prpt作成」（毎日）: 人が claude.ai の Routines 画面で一時停止する
- Cloud Routine「【口コミパワー】 Instagram 投稿分析取得」: 既に無効

## 移行先での扱い

- アカ定義: instagram-engine `accounts/kuchikomi/persona.yaml`＋`rules.md`（genre: meo-saas）
- リール: Phase 4（テンプレートエンジン稼働後・転職アカと同時期）に開始
- カルーセル: Phase 5（フィード統合）で engine から再開。Airtable は廃止対象
- 本リポジトリのQAサブエージェント（instagram-image-qa / fail-triage）の判定観点は
  engine の `audit/`（G2ルーブリック）へ吸収する
- 移行完了後、このリポジトリはアーカイブする
