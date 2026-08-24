import calendar
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import re
import smtplib
import socket
import time
import urllib.parse
import urllib.request

import feedparser
from google import genai

# ============================================================
# タイムアウト設定（フリーズ対策）
# ============================================================
socket.setdefaulttimeout(10)

# ============================================================
# 設定
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

# 送信先（環境変数 TO_EMAILS からカンマ区切りで取得）
TO_EMAILS_ENV = os.environ.get("TO_EMAILS", "")
TO_EMAILS = [email.strip() for email in TO_EMAILS_ENV.split(",") if email.strip()]

# Geminiで使用するモデル
GEMINI_MODEL = "gemini-3.6-flash"

# 1日にメールへ掲載するニュース数
MAX_ARTICLES = 10

# 1つのRSSフィードから取得する最大件数
MAX_ENTRIES_PER_FEED = 10

# ニュースの対象時間（時間単位: 28時間）
MAX_AGE_HOURS = 28

# 除外キーワード（株価・株式関連）
EXCLUDE_KEYWORDS = [
    "株価", "株式", "株高", "株安", "日経平均", "TOPIX", "銘柄",
    "stock price", "stock market", "shares", "equity", "wall street"
]


# ============================================================
# RSS取得先リスト（Google News ＋ 専門ニュースサイト）
# ============================================================

JP_QUERY = urllib.parse.quote(
    '("宇宙" OR "衛星") AND ("安全保障" OR "防衛" OR "軍事" OR "自衛隊") when:30h'
)

EN_QUERY = urllib.parse.quote(
    '("space security" OR "space force" OR "satellite" OR "military") when:30h'
)

RSS_URLS = [
    f"https://news.google.com/rss/search?q={JP_QUERY}&hl=ja&gl=JP&ceid=JP:ja",
    f"https://news.google.com/rss/search?q={EN_QUERY}&hl=en-US&gl=US&ceid=US:en",
    "https://spacenews.com/feed",                           # SpaceNews
    "https://feeds.feedburner.com/BreakingDefense",         # Breaking Defense
    "https://www.defenseone.com/rss/all",                  # Defense One
]


# ============================================================
# 補助関数
# ============================================================

def clean_html(text):
    """HTMLタグ・特殊文字を除去"""
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


def is_stock_related(title, summary):
    """株価・株式関連ニュースか判定"""
    text = f"{title} {summary}".lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def is_within_target_hours(entry):
    """指定時間内のニュースか判定"""
    published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not published_parsed:
        return True

    published_timestamp = calendar.timegm(published_parsed)
    current_timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()
    age_hours = (current_timestamp - published_timestamp) / 3600

    return age_hours <= MAX_AGE_HOURS


# ============================================================
# ニュース取得
# ============================================================

def fetch_latest_news():
    articles = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for url in RSS_URLS:
        print(f"RSS取得中: {url}")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                feed = feedparser.parse(response.read())

            entries = feed.entries[:MAX_ENTRIES_PER_FEED]
            filtered_count = 0

            for entry in entries:
                if not is_within_target_hours(entry):
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "") or entry.get("id", "")
                summary = clean_html(entry.get("summary", "").strip() or entry.get("description", "").strip())
                if not summary:
                    summary = title

                # 株価関連ニュースを除外
                if is_stock_related(title, summary):
                    print(f"  └ 除外(株価関連): {title[:40]}")
                    continue

                if title:
                    articles.append({
                        "title": title,
                        "link": link if link else "https://news.google.com/",
                        "summary": summary,
                    })
                    filtered_count += 1

            print(f"  └ 28時間以内の対象: {filtered_count}件")

        except Exception as e:
            print(f"  └ RSS取得エラー (スキップします): {e}")

    return articles


# ============================================================
# Gemini処理（個別要約・全体まとめ）
# ============================================================

def summarize_article(client, article):
    """個別ニュースの3行要約（※URLは含めない）"""
    prompt = f"""
以下のニュース記事を読み込み、宇宙・安全保障の観点から要約と重要度評価を行ってください。
英語の場合はタイトルと要約を自然な日本語に翻訳してください。

【記事タイトル】: {article['title']}
【記事概要】: {article['summary']}

【出力フォーマット】（以下の形式を厳守し、URLは出力しないでください）
■ タイトル: [日本語タイトル]
■ 重要度: [★1〜★5]（理由: 簡潔に記述）
■ 3行要約:
- [要約1]
- [要約2]
- [要約3]
"""
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    if not response or not response.text:
        raise ValueError("Geminiから空の応答が返されました。")
    return response.text.strip()


def generate_overall_summary(client, summarized_texts):
    """全記事を俯瞰した『今日のニュースまとめ』の生成"""
    all_content = "\n\n".join(summarized_texts)
    prompt = f"""
以下は本日収集された宇宙・安全保障に関する主要ニュースの要約一覧です。
これらを全体的に俯瞰し、本日の主な動向や注目点を3〜5文程度（または3箇条書き）で「今日のニュースまとめ」として記述してください。

【ニュース一覧】
{all_content}

【出力フォーマット】
【今日のニュースまとめ】
・[全体動向1]
・[全体動向2]
・[全体動向3]
"""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"全体まとめ生成エラー: {e}")
    
    return "【今日のニュースまとめ】\n本日検出されたニュースの個別詳細は以下をご確認ください。"


# ============================================================
# メール送信
# ============================================================

def send_email(subject, body):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not TO_EMAILS:
        raise ValueError("メール設定（GMAIL_USER / GMAIL_APP_PASSWORD / TO_EMAILS）が不十分です。")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        for to_email in TO_EMAILS:
            msg = MIMEMultipart()
            msg["From"] = GMAIL_USER
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))
            server.send_message(msg)
            print(f"  └ 送信完了: {to_email}")


# ============================================================
# メイン処理
# ============================================================

def main():
    print("=" * 60)
    print("宇宙・安全保障ニュース自動配信")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が設定されていません。")
        return

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Gemini初期化エラー: {e}")
        return

    articles = fetch_latest_news()
    print(f"\n検出された合計記事数: {len(articles)}件")

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    email_subject = f"【日刊】宇宙・安全保障 ニュースまとめ ({today_str})"

    if not articles:
        print("直近28時間以内の該当ニュース記事がありませんでした。")
        send_email(email_subject, f"{today_str} の宇宙・安全保障ニュースです。\n\n該当する最新ニュースは検出されませんでした。")
        return

    summarized_results = []
    url_list = []
    seen_titles = set()
    success_count = 0

    print("\nAI要約処理の開始")
    for article in articles:
        title_key = article["title"][:50].lower().strip()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        try:
            summary_text = summarize_article(client, article)
            summarized_results.append(summary_text)
            url_list.append(f"・{article['title']}\n  {article['link']}")
            success_count += 1
            print(f"  └ 要約成功: {article['title'][:40]}")
        except Exception as e:
            print(f"  └ 要約エラー: {e}")

        if len(summarized_results) >= MAX_ARTICLES:
            break

        time.sleep(1)

    # --------------------------------------------------------
    # 全体の「今日のニュースまとめ」を生成
    # --------------------------------------------------------
    print("\n「今日のニュースまとめ」の生成中...")
    overall_summary = generate_overall_summary(client, summarized_results)

    # --------------------------------------------------------
    # メール本文の構築
    # --------------------------------------------------------
    divider = "\n\n" + ("=" * 50) + "\n\n"
    
    # 1. ヘッダー & 今日のニュースまとめ
    email_body = f"{today_str} の宇宙・安全保障ニュース（主要{len(summarized_results)}件）\n\n"
    email_body += overall_summary + divider

    # 2. 個別ニュースの3行要約一覧
    email_body += divider.join(summarized_results) + divider

    # 3. 参照URL一覧（末尾に一括配置）
    email_body += "【参照URL一覧】\n" + "\n".join(url_list)

    # --------------------------------------------------------
    # 送信
    # --------------------------------------------------------
    print("\nメール送信中...")
    try:
        send_email(email_subject, email_body)
        print("送信完了しました！")
    except Exception as e:
        print(f"送信エラー: {e}")

if __name__ == "__main__":
    main()
