# 宇宙安全保障 政策・分析レポート自動配信システム

日本の防衛・宇宙安全保障に大きな影響を与える最新ニュースを自動収集し、Gemini API を活用して「**インテリジェンス・アナリシス（戦略評価・So What分析）**」を行った上で、毎日メール配信する Python スクリプトおよび GitHub Actions ワークフローです。

---

## 📌 特長

* **アナリスト視点の高度な分析**:
  * 単なる要約にとどまらず、**事実（Fact）**、**安全保障上のインプリケーション（So What?）**、**今後の注視点（Watch Items）** に構造化して出力。
  * メール冒頭に全体を俯瞰した「エグゼクティブ・サマリー（本日の戦略評価）」を自動生成。
* **主要アクター・ドメインへのフォーカス**:
  * 米国、中国、ロシア、北朝鮮等の動向や、SDA/SSA、PNT、ISR、ASAT などの宇宙防衛領域に与えるインパクトを評価。
* **ノイズ・株価ニュースの除外**:
  * 株式情報・市場トピックなどの不必要なニュースを自動フィルタリング。
* **Gemini API 無料枠への最適化**:
  * 複数記事を 1 回の API リクエストで一括分析（バッチ処理）することで、`429 RESOURCE_EXHAUSTED`（Quotaエラー）を回避し、無料枠内（1日20リクエスト）で安定稼働。

---

## ⚙️ システム構成と仕組み

1. **ニュース収集（RSS）**: Google News RSS（日・英）および海外の主要防衛専門メディア（SpaceNews, Breaking Defense, Defense One）から直近28時間以内の記事を取得。
2. **フィルタリング**: 株価関連キーワードの除外および重複タイトルのチェック。
3. **AI分析（Gemini API）**: `google-genai` SDK を用い、専門家向けプロンプトで一括分析。
4. **配信（Gmail SMTP）**: 生成されたレポートと情報ソース一覧（URL）をまとめたメールを指定アドレス宛に送信。

---

## 🚀 準備・セットアップ

### 1. 必要な環境変数・GitHub Secrets の設定

GitHub リポジトリの **Settings > Secrets and variables > Actions** にて、以下の Secrets を登録してください。

| Secret 名 | 説明 |
| :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio で取得した Gemini API キー |
| `GMAIL_USER` | 送信元となる Gmail アドレス |
| `GMAIL_APP_PASSWORD` | Gmail のアプリパスワード（Google アカウントの「2段階認証」設定から取得） |
| `TO_EMAILS` | 送信先メールアドレス（カンマ区切りで複数指定可能。例: `a@example.com,b@example.com`） |

---

### 2. ローカル環境での実行・テスト

```bash
# 依存ライブラリのインストール
pip install google-genai feedparser

# 環境変数をセットして実行 (Linux/macOS)
export GEMINI_API_KEY="your_api_key"
export GMAIL_USER="your_email@gmail.com"
export GMAIL_APP_PASSWORD="your_app_password"
export TO_EMAILS="destination@example.com"

python main.py
