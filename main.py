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

# ============================================================
# 設定
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

TO_EMAIL = "minamix.com@gmail.com"

# 正式なモデル名を指定
GEMINI_MODEL = "gemini-2.0-flash"

MAX_ARTICLES = 8


# ============================================================
# Google News RSS（検索クエリを拡張）
# ============================================================

JP_QUERY = urllib.parse.quote("宇宙 (安全保障 OR 防衛 OR 衛星 OR ミサイル)")
EN_QUERY = urllib.parse.quote('("space security" OR "space defense" OR "military space")')

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
]


# ============================================================
# HTML除去
# ============================================================

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
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ============================================================
# ニュース取得
# ============================================================

def fetch_latest_news():
    articles = []

    for url in RSS_URLS:
        print(f"RSS取得中: {url}")
        try:
            feed = feedparser.parse(url)
            print(f"  └ 取得件数: {len(feed.entries)}件")

            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "") or entry.get("id", "")
                summary = clean_html(entry.get("summary", "").strip())

                if not summary:
                    summary = title

                if title:
                    articles.append(
                        {
                            "title": title,
                            "link": link if link else "https://news.google.com/",
                            "summary": summary,
                        }
                    )
        except Exception as e:
            print(f"  └ RSS取得エラー: {e}")

    return articles


# ============================================================
# Geminiによるニュース要約
# ============================================================

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
        model= GEMINI_MODEL,
        contents=prompt,
    )

    if response is None or not response.text:
        raise ValueError("Geminiからの応答が空でした。")

    return response.text.strip()


def create_error_summary(article):
    return (
        f"■ タイトル: {article['title']}\n"
        f"■ AI要約: 今回はAIによる要約を取得できませんでした。\n"
        f"■ URL: {article['link']}"
    )


# ============================================================
# メール送信
# ============================================================

def send_email(subject, body):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not TO_EMAIL:
        raise ValueError("メール送信に必要な環境変数が不足しています。")

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


# ============================================================
# メイン処理
# ============================================================

def main():
    print("=" * 60)
    print("宇宙・安全保障ニュース自動配信")
    print("=" * 60)

    print("1. Gemini APIクライアントの初期化")
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    print(f"使用Geminiモデル: {GEMINI_MODEL}")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Geminiクライアント初期化エラー: {e}")
        return

    print("\n2. ニュース記事の取得")
    articles = fetch_latest_news()
    print(f"検出された合計記事数: {len(articles)}件")

    if not articles:
        print("ニュース記事が1件も取得できませんでした。")
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"
        email_body = f"{today_str} の宇宙・安全保障ニュースです。\n\n本日は該当する最新ニュースが検出されませんでした。"
        send_email(email_subject, email_body)
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
            if summary_text:
                summarized_results.append(summary_text)
                success_count += 1
                print("  └ 要約成功")
            else:
                summarized_results.append(create_error_summary(article))
                error_count += 1
        except Exception as e:
            error_count += 1
            print(f"  └ 要約エラー: {e}")
            summarized_results.append(create_error_summary(article))

        if len(summarized_results) >= MAX_ARTICLES:
            break

        time.sleep(1)

    print("\n4. 要約処理結果")
    print(f"成功: {success_count}件 / 失敗: {error_count}件 / メール掲載: {len(summarized_results)}件")

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"
    divider = "\n\n" + ("=" * 50) + "\n\n"

    email_body = (
        f"{today_str} の宇宙・安全保障に関する主要ニュース（{len(summarized_results)}件）です。\n\n"
        f"AI要約成功: {success_count}件\nAI要約失敗: {error_count}件\n"
        + divider
        + divider.join(summarized_results)
    )

    print("\n5. メール送信")
    send_email(email_subject, email_body)
    print("送信完了しました！")
    print("=" * 60)


if __name__ == "__main__":
    main()
