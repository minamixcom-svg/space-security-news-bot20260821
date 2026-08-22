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

# 送信先
TO_EMAIL = "minamix.com@gmail.com"

# Geminiで使用するモデル
# 以前の gemini-2.0-flash / gemini-2.5-flash から変更
GEMINI_MODEL = "gemini-2.0-flash"

# 1日にメールへ掲載するニュース数
MAX_ARTICLES = 8


# ============================================================
# Google News RSS
# ============================================================

JP_QUERY = urllib.parse.quote("宇宙 安全保障")
EN_QUERY = urllib.parse.quote("space security")

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
]


# ============================================================
# HTML除去
# ============================================================

def clean_html(text):
    """
    Google News RSSのsummaryにはHTMLタグが含まれる場合があるため、
    HTMLタグを除去してプレーンテキストにする。
    """
    if not text:
        return ""

    # HTMLタグを削除
    text = re.sub(r"<[^>]+>", " ", text)

    # HTMLエンティティを簡易的に処理
    text = (
        text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
    )

    # 連続する空白を整理
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

                link = (
                    entry.get("link", "")
                    or entry.get("id", "")
                )

                summary = entry.get("summary", "").strip()

                summary = clean_html(summary)

                # summaryが空の場合はタイトルを使用
                if not summary:
                    summary = title

                if title:
                    articles.append(
                        {
                            "title": title,
                            "link": (
                                link
                                if link
                                else "https://news.google.com/"
                            ),
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
以下のニュース記事情報を読み込み、
宇宙・安全保障の観点から要約と重要度評価を行ってください。

記事が英語の場合は、
タイトルと要約を自然な日本語に翻訳してください。

特に以下の観点を重視してください。

・宇宙安全保障への影響
・軍事・防衛への影響
・米国、中国、日本、欧州など主要国への影響
・衛星、宇宙軍、ミサイル防衛、宇宙作戦などとの関係
・今後の安全保障環境への影響

【記事タイトル】
{article['title']}

【記事概要】
{article['summary']}

【出力フォーマット】
以下の形式を厳守してください。

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

    # Geminiから応答が返ってこなかった場合
    if response is None:
        raise ValueError("Geminiから応答が返されませんでした。")

    if not response.text:
        raise ValueError("Geminiから空の応答が返されました。")

    return response.text.strip()


# ============================================================
# 要約失敗時のメール掲載用テキスト
# ============================================================

def create_error_summary(article):
    """
    Geminiによる要約に失敗した場合でも、
    ニュースそのものをメールに残す。
    """

    return (
        f"■ タイトル: {article['title']}\n"
        f"■ AI要約: 今回はAIによる要約を取得できませんでした。\n"
        f"■ URL: {article['link']}"
    )


# ============================================================
# メール送信
# ============================================================

def send_email(subject, body):

    if not GMAIL_USER:
        raise ValueError("GMAIL_USER が設定されていません。")

    if not GMAIL_APP_PASSWORD:
        raise ValueError(
            "GMAIL_APP_PASSWORD が設定されていません。"
        )

    if not TO_EMAIL:
        raise ValueError("TO_EMAIL が設定されていません。")

    msg = MIMEMultipart()

    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    msg.attach(
        MIMEText(
            body,
            "plain",
            "utf-8"
        )
    )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as server:

        server.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )

        server.send_message(msg)


# ============================================================
# メイン処理
# ============================================================

def main():

    print("=" * 60)
    print("宇宙・安全保障ニュース自動配信")
    print("=" * 60)

    # --------------------------------------------------------
    # 1. Gemini APIクライアント初期化
    # --------------------------------------------------------

    print("1. Gemini APIクライアントの初期化")

    if not GEMINI_API_KEY:
        print(
            "エラー: GEMINI_API_KEY が設定されていません。"
        )
        return

    print(
        f"使用Geminiモデル: {GEMINI_MODEL}"
    )

    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

    except Exception as e:
        print(
            f"Geminiクライアント初期化エラー: {e}"
        )
        return

    # --------------------------------------------------------
    # 2. ニュース記事取得
    # --------------------------------------------------------

    print("\n2. ニュース記事の取得")

    articles = fetch_latest_news()

    print(
        f"検出された合計記事数: "
        f"{len(articles)}件"
    )

    if not articles:

        print(
            "ニュース記事が1件も取得できませんでした。"
        )

        today_str = datetime.date.today().strftime(
            "%Y-%m-%d"
        )

        email_subject = (
            f"【日刊】宇宙・安全保障 "
            f"ニュースまとめ ({today_str})"
        )

        email_body = (
            f"{today_str} の宇宙・安全保障ニュースです。\n\n"
            "本日は該当する最新ニュースが"
            "検出されませんでした。"
        )

        try:
            send_email(
                email_subject,
                email_body
            )

            print("ニュースなしメールを送信しました。")

        except Exception as e:
            print(
                f"メール送信エラー: {e}"
            )

        return

    # --------------------------------------------------------
    # 3. AI要約
    # --------------------------------------------------------

    summarized_results = []

    seen_titles = set()

    success_count = 0
    error_count = 0

    print("\n3. AI要約処理の開始")

    for article in articles:

        # タイトルの先頭50文字を重複判定に使用
        title_key = (
            article["title"][:50]
            .lower()
            .strip()
        )

        if title_key in seen_titles:
            print(
                f"  └ 重複記事をスキップ: "
                f"{article['title'][:50]}"
            )
            continue

        seen_titles.add(title_key)

        print(
            f"\n[{success_count + error_count + 1}件目]"
        )

        print(
            f"タイトル: "
            f"{article['title'][:80]}"
        )

        try:

            print("  └ Geminiによる要約中...")

            summary_text = summarize_article(
                client,
                article
            )

            if summary_text:

                summarized_results.append(
                    summary_text
                )

                success_count += 1

                print("  └ 要約成功")

            else:

                print(
                    "  └ 警告: "
                    "生成テキストが空でした"
                )

                summarized_results.append(
                    create_error_summary(article)
                )

                error_count += 1

        except Exception as e:

            error_count += 1

            print(
                f"  └ 要約エラー: {e}"
            )

            # 要約に失敗してもニュースをメールに残す
            summarized_results.append(
                create_error_summary(article)
            )

        # 成功＋失敗を合わせて最大8件
        if len(summarized_results) >= MAX_ARTICLES:
            break

        # APIへの連続アクセスを少し間隔を空ける
        time.sleep(1)

    # --------------------------------------------------------
    # 4. 要約結果確認
    # --------------------------------------------------------

    print("\n4. 要約処理結果")

    print(
        f"成功: {success_count}件"
    )

    print(
        f"失敗: {error_count}件"
    )

    print(
        f"メール掲載予定: "
        f"{len(summarized_results)}件"
    )

    # --------------------------------------------------------
    # 5. メール本文作成
    # --------------------------------------------------------

    today_str = datetime.date.today().strftime(
        "%Y-%m-%d"
    )

    email_subject = (
        f"【日刊】宇宙・安全保障 "
        f"ニュースまとめ ({today_str})"
    )

    divider = (
        "\n\n"
        + ("=" * 50)
        + "\n\n"
    )

    if summarized_results:

        email_body = (
            f"{today_str} の宇宙・安全保障に関する"
            f"主要ニュース "
            f"（{len(summarized_results)}件）です。\n\n"
        )

        email_body += (
            f"AI要約成功: {success_count}件\n"
            f"AI要約失敗: {error_count}件\n"
        )

        email_body += (
            divider
            + divider.join(summarized_results)
        )

    else:

        # 万一の場合でも本文が空にならないようにする
        email_body = (
            f"{today_str} の宇宙・安全保障ニュースです。\n\n"
            "ニュースの取得またはAI要約に失敗しました。\n"
            "実行ログを確認してください。"
        )

    # --------------------------------------------------------
    # 6. メール送信
    # --------------------------------------------------------

    print("\n5. メール送信")

    print(
        f"送信先: {TO_EMAIL}"
    )

    try:

        send_email(
            email_subject,
            email_body
        )

        print(
            "送信完了しました！"
        )

    except Exception as e:

        print(
            f"メール送信エラー: {e}"
        )

    print("=" * 60)
    print("処理終了")
    print("=" * 60)


# ============================================================
# エントリーポイント
# ============================================================

if __name__ == "__main__":
    main()
