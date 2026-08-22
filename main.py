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

JP_QUERY = urllib.parse.quote("宇宙 安全保障")
EN_QUERY = urllib.parse.quote("space security")

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
]


def fetch_latest_news():
    articles = []
    for url in RSS_URLS:
        print(f"RSS取得中: {url}")
        feed = feedparser.parse(url)
        print(f"  └ 取得件数: {len(feed.entries)}件")
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "") or entry.get("id", "")
            summary = entry.get("summary", "").strip() or title

            if title:
                articles.append(
                    {
                        "title": title,
                        "link": link if link else "https://news.google.com/",
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
    # 互換性のある正式モデル名「gemini-2.0-flash」を指定
    response = client.models.generate_content(
        model="gemini-3.6-flash",
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
    print("1. Gemini APIクライアントの初期化")
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return
    client = genai.Client(api_key=GEMINI_API_KEY)

    print("2. ニュース記事の取得")
    articles = fetch_latest_news()
    print(f"検出された合計記事数: {len(articles)}件")

    if not articles:
        print("ニュース記事が1件も取得できませんでした。")
        send_email(
            f"【日刊】宇宙・安全保障 ニュースまとめ ({datetime.date.today()})",
            "本日は該当する最新ニュースが検出されませんでした。",
        )
        return

    summarized_results = []
    seen_titles = set()
    count = 0

    print("3. AI要約処理の開始")
    for article in articles:
        title_key = article["title"][:30].lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        try:
            print(f"[{count + 1}件目要約中] {article['title'][:30]}...")
            summary_text = summarize_article(client, article)

            if summary_text:
                summarized_results.append(summary_text)
                count += 1
                print("  └ 成功")
            else:
                print("  └ 警告: 生成テキストが空でした")

            if count >= 8:
                break

            time.sleep(1)

        except Exception as e:
            print(f"  └ 要約エラー: {e}")

    print(f"作成完了した要約件数: {len(summarized_results)}件")

    if not summarized_results:
        print("要約結果が1件も作成されなかったため、メール送信を中断しました。")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"

    divider = "\n\n" + ("=" * 40) + "\n\n"
    email_body = f"{today_str} の宇宙・安全保障に関する主要ニュース（{len(summarized_results)}件）です。\n\n"
    email_body += divider + divider.join(summarized_results)

    print("4. メール送信")
    send_email(email_subject, email_body)
    print("送信完了しました！")


if __name__ == "__main__":
    main()
