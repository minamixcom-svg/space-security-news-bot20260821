import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import re
import smtplib
import time
import urllib.parse

import feedparser
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TO_EMAIL = "minamix.com@gmail.com"

# 確実に動作する標準安定モデル
GEMINI_MODEL = "gemini-1.5-flash"
MAX_ARTICLES = 8

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


def fix_google_news_link(link):
    """
    Google News RSSの暗号化URLをiPhone等で正常に開ける形式に補正
    """
    if not link:
        return "https://news.google.com/"
    # Google Newsのトラッキング付き直リンクを展開
    if "news.google.com" in link and "/articles/" in link:
        return link.replace("./articles/", "https://news.google.com/articles/")
    return link


def fetch_latest_news():
    articles = []
    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                raw_link = entry.get("link", "") or entry.get("id", "")
                link = fix_google_news_link(raw_link)
                summary = clean_html(entry.get("summary", "").strip()) or title

                if title:
                    articles.append({
                        "title": title,
                        "link": link,
                        "summary": summary,
                    })
        except Exception as e:
            print(f"RSS取得エラー: {e}")
    return articles


def summarize_article(client, article):
    prompt = f"""
以下のニュース記事情報を読み込み、宇宙・安全保障の観点から要約と重要度評価を行ってください。
記事が英語の場合は、タイトルと要約を自然な日本語に翻訳してください。

【記事タイトル】
{article['title']}

【記事概要】
{article['summary']}

【出力フォーマット】
■ タイトル: [日本語タイトル]

■ 重要度: [★1〜★5]
（理由: 簡潔に記述）

■ 3行要約:
- [要約1]
- [要約2]
- [要約3]

■ URL: {article['link']}
"""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    if not response or not response.text:
        raise ValueError("Gemini応答が空です")
    return response.text.strip()


def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def main():
    print("=" * 60)
    print("宇宙・安全保障ニュース自動配信")
    print("=" * 60)

    print("1. Gemini APIクライアントの初期化")
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が未設定です。")
        return
    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"使用Geminiモデル: {GEMINI_MODEL}")

    print("\n2. ニュース記事の取得")
    articles = fetch_latest_news()
    print(f"検出された合計記事数: {len(articles)}件")

    if not articles:
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        send_email(
            f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})",
            "本日は該当する最新ニュースが検出されませんでした。"
        )
        return

    summarized_results = []
    seen_titles = set()
    success_count = 0
    error_count = 0

    print("\n3. AI要約処理の開始")
    for article in articles:
        title_key = article["title"][:50].lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        print(f"\n[{success_count + error_count + 1}件目] タイトル: {article['title'][:80]}")

        try:
            print("  └ Geminiによる要約中...")
            summary_text = summarize_article(client, article)
            summarized_results.append(summary_text)
            success_count += 1
            print("  └ 要約成功")
        except Exception as e:
            error_count += 1
            print(f"  └ 要約エラー: {e}")

        if len(summarized_results) >= MAX_ARTICLES:
            break
        time.sleep(1)

    print("\n4. 要約処理結果")
    print(f"成功: {success_count}件 / 失敗: {error_count}件 / メール掲載: {len(summarized_results)}件")

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"
    divider = "\n\n" + ("=" * 50) + "\n\n"

    if summarized_results:
        email_body = (
            f"{today_str} の宇宙・安全保障に関する主要ニュース（{len(summarized_results)}件）です。\n\n"
            f"AI要約成功: {success_count}件\nAI要約失敗: {error_count}件\n"
            + divider
            + divider.join(summarized_results)
        )
    else:
        email_body = f"{today_str} のニュース要約生成に失敗しました。"

    print("\n5. メール送信")
    send_email(email_subject, email_body)
    print("送信完了しました！")
    print("=" * 60)


if __name__ == "__main__":
    main()
