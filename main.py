import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import time
import urllib.parse
import feedparser
from google import genai

# 設定情報
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TO_EMAIL = "minamix.com@gmail.com"

# 検索キーワード（日本語・英語）
# より広範囲の記事を取得できるようにクエリを最適化
JP_QUERY = urllib.parse.quote("宇宙 (安全保障 OR 防衛 OR 衛星 OR ミサイル)")
EN_QUERY = urllib.parse.quote(
    '("space security" OR "space defense" OR "military space")'
)

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
]

client = genai.Client(api_key=GEMINI_API_KEY)


def fetch_latest_news():
    articles = []
    now = time.time()
    # 取得範囲を過去36時間に拡大（土日やニュースが少ない日対策）
    time_limit_sec = 36 * 60 * 60

    for url in RSS_URLS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            published_parsed = entry.get("published_parsed")
            if published_parsed:
                published_time = time.mktime(published_parsed)
                if now - published_time <= time_limit_sec:
                    articles.append(
                        {
                            "title": entry.title,
                            "link": entry.link,
                            "summary": entry.get("summary", ""),
                        }
                    )
    return articles


def summarize_article(article):
    prompt = f"""
以下のニュース記事情報を読み込み、宇宙・安全保障の観点から要約と重要度評価を行ってください。
記事が英語の場合は、タイトルと要約を自然な日本語に翻訳してください。

【記事タイトル】: {article['title']}
【記事概要】: {article['summary']}

【出力フォーマット】（以下の形式厳守で出力してください）
■ タイトル: [日本語タイトル]
■ 重要度: [★1〜★5]（理由: 簡潔に記述）
■ 3行要約:
- [要約1]
- [要約2]
- [要約3]
■ URL: {article['link']}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
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
    print("ニュース記事を取得中...")
    articles = fetch_latest_news()

    if not articles:
        print("該当するニュース記事が見つかりませんでした。")
        send_email(
            f"【日刊】宇宙・安全保障 ニュースまとめ ({datetime.date.today()})",
            "本日は該当する最新ニュースが検出されませんでした。",
        )
        return

    print(f"{len(articles)}件の記事を検出。AI要約を開始します...")
    summarized_results = []
    seen_links = set()

    # 最大10件まで要約（API制限・メール長すぎ対策）
    count = 0
    for article in articles:
        if article["link"] in seen_links:
            continue
        seen_links.add(article["link"])

        try:
            summary_text = summarize_article(article)
            summarized_results.append(summary_text)
            count += 1
            if count >= 10:
                break
        except Exception as e:
            print(f"要約エラー ({article['title']}): {e}")

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"
    email_body = f"{today_str} の宇宙・安全保障に関する主要ニュース（{len(summarized_results)}件）です。\n\n"
    email_body += "\n\n" + ("=" * 40) + "\n\n"
    email_body += "\n\n" + ("=" * 40) + "\n\n".join(summarized_results)

    send_email(email_subject, email_body)
    print("送信完了しました。")


if __name__ == "__main__":
    main()
