import os
print("【デバッグ情報】実行中のファイルパス:", os.path.abspath(__file__))
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import re
import smtplib
import traceback
import urllib.parse

import feedparser
from google import genai
from googlenewsdecoder import new_decodurl

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TO_EMAIL = "minamix.com@gmail.com"

# 安定して動作する標準モデル
GEMINI_MODEL = "gemini-3.6-flash"
print("【確認】GEMINI_MODEL =", GEMINI_MODEL)
MAX_ARTICLES = 10

JP_QUERY = urllib.parse.quote("宇宙 (安全保障 OR 防衛 OR 衛星 OR ミサイル)")
EN_QUERY = urllib.parse.quote('("space security" OR "space defense" OR "military space")')

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
]


def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


def resolve_link(google_url):
    try:
        decoded = new_decodurl(google_url)
        if decoded and decoded.get("status") and decoded.get("decoded_url"):
            return decoded["decoded_url"]
    except Exception as e:
        print(f"  └ URLデコード失敗: {e}")
    return google_url


def fetch_latest_news():
    articles = []
    seen_titles = set()

    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                title_key = title[:40].lower()

                if not title or title_key in seen_titles:
                    continue

                seen_titles.add(title_key)
                raw_link = entry.get("link", "") or entry.get("id", "")
                real_link = resolve_link(raw_link)
                summary = clean_html(entry.get("summary", "").strip()) or title

                articles.append({
                    "title": title,
                    "link": real_link,
                    "summary": summary,
                })

                if len(articles) >= MAX_ARTICLES:
                    break
        except Exception as e:
            print(f"RSS取得エラー: {e}")

        if len(articles) >= MAX_ARTICLES:
            break

    return articles


def summarize_all_news(client, articles):
    articles_text = ""
    for idx, item in enumerate(articles, 1):
        articles_text += f"【記事{idx}】\nタイトル: {item['title']}\n概要: {item['summary']}\nURL: {item['link']}\n\n"

    prompt = f"""
あなたは宇宙・安全保障分野の専門アナリストです。
以下に提供された本日の主要ニュース群（全{len(articles)}件）を横断的に分析し、全体の潮流・動向についての「総括レポート」を作成してください。

【収集されたニュース一覧】
{articles_text}

【出力フォーマット】
以下の構成で出力してください（Markdown形式）。

1. 本日の総括サマリー（3行〜5行程度）
・本日収集されたニュース全体の共通テーマや、宇宙安全保障における最大の注目ポイントを要約してください。

2. 主なトピック・動向（2〜3項目）
・関連するニュースをグループ化し、どのような動きがあるかをリスト形式で解説してください。

3. 各ニュース記事一覧
・提供された全ニュースについて、日本語に統一したタイトルとリンクを一覧化してください。
・フォーマット:
  - [日本語タイトル](URL)
"""

    response = client.models.generate_content(
        GEMINI_MODEL = "gemini-3.6-flash"
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response or not response.text:
        raise ValueError("Gemini APIからの応答テキストが空です。")
    return response.text.strip()


def send_html_email(subject, text_content):
    msg = MIMEMultipart("alternative")
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    html_body = text_content.replace("\n", "<br>")
    html_body = re.sub(
        r'\[(.*?)\]\((https?://.*?)\)',
        r'<a href="\2" style="color: #1a73e8; text-decoration: underline;">\1</a>',
        html_body
    )

    full_html = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; padding: 15px;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; padding: 20px; border: 1px solid #e0e0e0;">
          {html_body}
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(full_html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def main():
    print("=" * 60)
    print("★★★ 【最新コード実行中】宇宙・安全保障 ニュース総括 ★★★")
    print("=" * 60)

    print("1. Gemini APIクライアント初期化")
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が環境変数に設定されていません。")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"使用モデル: {GEMINI_MODEL}")

    print("\n2. ニュース記事の取得とURL解読中...")
    articles = fetch_latest_news()
    print(f"  └ 有効な記事数: {len(articles)}件")

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊総括】宇宙・安全保障 ニュースダイジェスト ({today_str})"

    if not articles:
        print("ニュース記事が取得できませんでした。")
        send_html_email(email_subject, f"{today_str} 本日は該当するニュースが検出されませんでした。")
        return

    print("\n3. AIによる全体総括・傾向分析の生成中...")
    try:
        overall_summary = summarize_all_news(client, articles)
        print("  └ 総括の生成に成功しました！")
    except Exception as e:
        print(f"  └ AI分析中にエラーが発生しました: {e}")
        print("--- 詳細エラーログ ---")
        traceback.print_exc()
        print("----------------------")
        overall_summary = f"※ AI要約の生成中にエラーが発生したため、ニュース一覧のみを送信します。\nエラー理由: {e}\n\n【収集記事一覧】\n" + "\n".join([f"- [{a['title']}]({a['link']})" for a in articles])

    email_body = f"■ {today_str} 宇宙・安全保障トピックス分析\n\n" + overall_summary

    print("\n4. メール送信中...")
    try:
        send_html_email(email_subject, email_body)
        print("送信完了しました！")
    except Exception as e:
        print(f"メール送信エラー: {e}")

    print("=" * 60)


if __name__ == "__main__":
    main()
