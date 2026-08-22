import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import time
import urllib.parse
import feedparser
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
TO_EMAIL = "minamix.com@gmail.com"

# よりシンプルで広範囲にヒットする検索キーワードを設定
JP_QUERY = urllib.parse.quote("宇宙 安全保障")
EN_QUERY = urllib.parse.quote("space security")

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
]


def fetch_latest_news():
    articles = []

    for url in RSS_URLS:
        print(f"RSS取得試行: {url}")
        feed = feedparser.parse(url)
        print(f"取得できたエントリ数: {len(feed.entries)}")

        for entry in feed.entries:
            title = entry.get("title", "")
            # linkまたはidからURLを取得
            link = entry.get("link", "") or entry.get("id", "")
            summary = entry.get("summary", "") or title

            if title and link:
                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "summary": summary,
                    }
                )
    return articles


def summarize_article(client, article):
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
        model="gemini-2.0-flash",
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
    print("1. Gemini APIクライアントを初期化中...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    print("2. ニュース記事を取得中...")
    articles = fetch_latest_news()
    print(f"検出された合計記事数: {len(articles)}")

    if not articles:
        print("ニュース記事が検出されませんでした。")
        send_email(
            f"【日刊】宇宙・安全保障 ニュースまとめ ({datetime.date.today()})",
            "本日は該当する最新ニュースが検出されませんでした。",
        )
        return

    summarized_results = []
    seen_links = set()
    count = 0

    for article in articles:
        if article["link"] in seen_links:
            continue
        seen_links.add(article["link"])

        try:
            summary_text = summarize_article(client, article)
            summarized_results.append(summary_text)
            count += 1
            print(f"要約成功 ({count}件目): {article['title'][:20]}...")
            if count >= 8:  # 8件に制限
                break
        except Exception as e:
            print(f"要約処理中にエラー発生: {e}")

    if not summarized_results:
        print("要約結果の生成に失敗しました。")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"
    email_body = f"{today_str} の宇宙・安全保障に関する主要ニュース（{len(summarized_results)}件）です。\n\n"
    email_body += "\n\n" + ("=" * 40) + "\n\n".join(summarized_results)

    print("3. メール送信中...")
    send_email(email_subject, email_body)
    print("送信完了！")


if __name__ == "__main__":
    main()
