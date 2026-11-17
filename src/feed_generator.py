from datetime import datetime, timezone
from email.utils import format_datetime
import html
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)


def ensure_podcast_cover(cover_path: Path, title: str) -> None:
    """確保存在符合 Apple Podcasts / Spotify 規範 (1400x1400 JPG) 的頻道封面圖。"""
    if cover_path.exists():
        return
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        size = 1400
        img = Image.new("RGB", (size, size), color=(18, 24, 41))
        draw = ImageDraw.Draw(img)

        # 繪製漸層背景裝飾圓框與卡片
        draw.rounded_rectangle(
            [(80, 80), (size - 80, size - 80)],
            radius=64,
            fill=(28, 38, 66),
            outline=(99, 102, 241),
            width=8,
        )
        draw.ellipse([(480, 220), (920, 660)], fill=(79, 70, 229))
        # 繪製簡易麥克風圖示
        draw.rounded_rectangle([(640, 310), (760, 490)], radius=60, fill=(255, 255, 255))
        draw.arc([(600, 380), (800, 550)], start=0, end=180, fill=(255, 255, 255), width=18)
        draw.line([(700, 550), (700, 610)], fill=(255, 255, 255), width=18)
        draw.line([(630, 610), (770, 610)], fill=(255, 255, 255), width=18)

        font_large = ImageFont.load_default(size=68)
        font_sub = ImageFont.load_default(size=44)

        draw.text(
            (size // 2, 820),
            "DAILY BILINGUAL",
            fill=(255, 255, 255),
            anchor="mm",
            font=font_large,
        )
        draw.text(
            (size // 2, 920),
            "REDDIT & NEWS PODCAST",
            fill=(165, 180, 252),
            anchor="mm",
            font=font_large,
        )
        draw.text(
            (size // 2, 1060),
            "5-Min Chinese + English Highlights",
            fill=(203, 213, 225),
            anchor="mm",
            font=font_sub,
        )

        img.save(cover_path, format="JPEG", quality=92)
        logger.info(f"已自動建立預設 1400x1400 Podcast 封面圖: {cover_path}")
    except Exception as e:
        logger.warning(f"建立預設封面圖時發生警告: {e}")


def format_duration_itunes(seconds: int) -> str:
    """將秒數轉為 HH:MM:SS 或 MM:SS 格式。"""
    mins, secs = divmod(max(1, int(seconds)), 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def build_episode_html_notes(ep: Dict[str, Any]) -> str:
    """產生顯示在 Podcast App (Show Notes) 裡的中英對照逐字稿與原文連結。"""
    parts: List[str] = []
    summary = ep.get("episode_summary", "")
    if summary:
        parts.append(f"<p>{html.escape(summary)}</p>")

    links = ep.get("selected_links", [])
    if links:
        parts.append("<h3>今日話題來源 (Sources)</h3><ul>")
        for link in links:
            t = html.escape(link.get("title", "Source"))
            u = html.escape(link.get("url", ""))
            if u:
                parts.append(f'<li><a href="{u}">{t}</a></li>')
            else:
                parts.append(f"<li>{t}</li>")
        parts.append("</ul>")

    segments = ep.get("segments", [])
    if segments:
        parts.append("<h3>中英雙語逐字稿 (Bilingual Transcript)</h3>")
        for idx, seg in enumerate(segments, start=1):
            zh = html.escape(seg.get("zh", ""))
            en = html.escape(seg.get("en", ""))
            parts.append(
                f"<p><strong>{idx}.</strong> {zh}<br/><em>{en}</em></p>"
            )

    return "\n".join(parts)


def prune_old_episodes(episodes_dir: Path, max_keep: int) -> List[Dict[str, Any]]:
    """讀取所有歷史單集 JSON 並依日期新到舊排序，若超過保留上限則自動清理舊檔。"""
    episodes_dir.mkdir(parents=True, exist_ok=True)
    json_files = sorted(episodes_dir.glob("*.json"), reverse=True)

    valid_episodes: List[Dict[str, Any]] = []
    for idx, jf in enumerate(json_files):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"讀取單集資訊失敗 ({jf}): {e}")
            continue

        mp3_file = episodes_dir / data.get("mp3_filename", f"{jf.stem}.mp3")
        if idx >= max_keep:
            logger.info(f"清理超過保留上限 ({max_keep}) 的舊單集: {jf.stem}")
            jf.unlink(missing_ok=True)
            mp3_file.unlink(missing_ok=True)
            continue

        if mp3_file.exists():
            valid_episodes.append(data)

    return valid_episodes


def update_feed_and_website(
    docs_dir: Path,
    config: Dict[str, Any],
) -> Path:
    """根據 docs/episodes 內的所有單集，重新產生符合 Apple/Spotify 標準的 feed.xml 與 index.html。"""
    pod_cfg = config.get("podcast", {})
    base_url = (
        os.environ.get("PODCAST_BASE_URL")
        or pod_cfg.get("base_url")
        or "https://YOUR_GITHUB_USERNAME.github.io/daily-bilingual-podcast"
    ).rstrip("/")
    email = (
        os.environ.get("PODCAST_EMAIL")
        or pod_cfg.get("email")
        or "your-email@example.com"
    ).strip()

    title = pod_cfg.get("title", "Reddit & News 每日五分鐘雙語精華")
    subtitle = pod_cfg.get("subtitle", "每天5分鐘，一句中文、一句英文")
    description = pod_cfg.get("description", subtitle)
    author = pod_cfg.get("author", "Daily Bilingual Podcast")
    language = pod_cfg.get("language", "zh-TW")
    category = pod_cfg.get("category", "News")
    subcategory = pod_cfg.get("subcategory", "Daily News")
    max_keep = int(pod_cfg.get("max_episodes_to_keep", 30))

    ensure_podcast_cover(docs_dir / "cover.jpg", title)

    episodes_dir = docs_dir / "episodes"
    episodes = prune_old_episodes(episodes_dir, max_keep=max_keep)

    feed_url = f"{base_url}/feed.xml"
    cover_url = f"{base_url}/cover.jpg"
    now_rfc2822 = format_datetime(datetime.now(timezone.utc))

    items_xml: List[str] = []
    for ep in episodes:
        ep_date = ep.get("date", "2026-01-01")
        ep_title = escape(ep.get("episode_title", f"Daily Bilingual ({ep_date})"))
        ep_summary = escape(ep.get("episode_summary", ""))
        mp3_filename = ep.get("mp3_filename", f"{ep_date}.mp3")
        mp3_url = f"{base_url}/episodes/{mp3_filename}"
        file_size = int(ep.get("file_size", 0))
        duration_str = format_duration_itunes(int(ep.get("duration_seconds", 300)))
        pub_date = ep.get("pub_date_rfc2822", now_rfc2822)
        guid = f"daily-bilingual-podcast-{ep_date}"
        html_notes = build_episode_html_notes(ep)

        items_xml.append(
            f"""    <item>
      <title>{ep_title}</title>
      <itunes:title>{ep_title}</itunes:title>
      <description>{ep_summary}</description>
      <itunes:summary>{ep_summary}</itunes:summary>
      <content:encoded><![CDATA[{html_notes}]]></content:encoded>
      <enclosure url="{escape(mp3_url)}" length="{file_size}" type="audio/mpeg"/>
      <guid isPermaLink="false">{escape(guid)}</guid>
      <pubDate>{pub_date}</pubDate>
      <itunes:duration>{duration_str}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
      <itunes:episodeType>full</itunes:episodeType>
    </item>"""
        )

    joined_items = "\n".join(items_xml)
    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(title)}</title>
    <link>{escape(base_url)}/</link>
    <atom:link href="{escape(feed_url)}" rel="self" type="application/rss+xml"/>
    <description>{escape(description)}</description>
    <itunes:subtitle>{escape(subtitle)}</itunes:subtitle>
    <itunes:summary>{escape(description)}</itunes:summary>
    <language>{escape(language)}</language>
    <itunes:author>{escape(author)}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:owner>
      <itunes:name>{escape(author)}</itunes:name>
      <itunes:email>{escape(email)}</itunes:email>
    </itunes:owner>
    <itunes:image href="{escape(cover_url)}"/>
    <image>
      <url>{escape(cover_url)}</url>
      <title>{escape(title)}</title>
      <link>{escape(base_url)}/</link>
    </image>
    <itunes:category text="{escape(category)}">
      <itunes:category text="{escape(subcategory)}"/>
    </itunes:category>
    <lastBuildDate>{now_rfc2822}</lastBuildDate>
{joined_items}
  </channel>
</rss>
"""

    feed_path = docs_dir / "feed.xml"
    feed_path.write_text(rss_xml, encoding="utf-8")
    logger.info(f"已更新 Podcast RSS Feed: {feed_path} (共 {len(episodes)} 集)")

    # 同步產生美觀的網頁版播放器與雙語逐字稿 (docs/index.html)
    generate_web_index(
        docs_dir=docs_dir,
        title=title,
        subtitle=subtitle,
        feed_url=feed_url,
        episodes=episodes,
    )
    # 防止 GitHub Pages 使用 Jekyll 忽略特定檔案
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")

    return feed_path


def generate_web_index(
    docs_dir: Path,
    title: str,
    subtitle: str,
    feed_url: str,
    episodes: List[Dict[str, Any]],
) -> None:
    """產生 GitHub Pages 首頁，提供線上收聽、中英逐字稿對照與一鍵複製 RSS 連結。"""
    cards_html: List[str] = []
    for ep in episodes:
        ep_date = html.escape(ep.get("date", ""))
        ep_title = html.escape(ep.get("episode_title", ""))
        ep_summary = html.escape(ep.get("episode_summary", ""))
        mp3_filename = html.escape(ep.get("mp3_filename", ""))
        duration_str = format_duration_itunes(int(ep.get("duration_seconds", 300)))

        transcript_rows: List[str] = []
        for idx, seg in enumerate(ep.get("segments", []), start=1):
            zh = html.escape(seg.get("zh", ""))
            en = html.escape(seg.get("en", ""))
            transcript_rows.append(
                f"""<div class="pair">
                  <div class="zh"><span class="num">{idx}.</span> {zh}</div>
                  <div class="en">{en}</div>
                </div>"""
            )
        joined_transcript = "\n".join(transcript_rows)

        cards_html.append(
            f"""
            <article class="card">
              <div class="meta">{ep_date} · 長度 {duration_str}</div>
              <h2>{ep_title}</h2>
              <p class="summary">{ep_summary}</p>
              <audio controls preload="none" src="episodes/{mp3_filename}"></audio>
              <details>
                <summary>展開中英雙語逐字稿 ({len(ep.get("segments", []))} 組句子)</summary>
                <div class="transcript">
                  {joined_transcript}
                </div>
              </details>
            </article>
            """
        )

    joined_cards = "\n".join(cards_html) or "<p>尚無單集，請先執行產生腳本。</p>"

    index_html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <link rel="alternate" type="application/rss+xml" title="{html.escape(title)}" href="feed.xml" />
  <style>
    :root {{
      --bg: #0f172a;
      --card: #1e293b;
      --accent: #6366f1;
      --text: #f8fafc;
      --muted: #94a3b8;
    }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}
    .container {{
      max-width: 820px;
      margin: 0 auto;
      padding: 40px 20px;
    }}
    header {{
      display: flex;
      gap: 24px;
      align-items: center;
      margin-bottom: 36px;
      flex-wrap: wrap;
    }}
    header img {{
      width: 120px;
      height: 120px;
      border-radius: 20px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    }}
    h1 {{ margin: 0 0 8px 0; font-size: 1.8rem; }}
    .sub {{ color: var(--muted); margin: 0 0 14px 0; }}
    .rss-box {{
      background: rgba(99, 102, 241, 0.15);
      border: 1px solid var(--accent);
      padding: 10px 14px;
      border-radius: 10px;
      font-size: 0.9rem;
      display: inline-flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .rss-box code {{ color: #c7d2fe; word-break: break-all; }}
    .card {{
      background: var(--card);
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.25);
    }}
    .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }}
    .card h2 {{ margin: 0 0 10px 0; font-size: 1.35rem; }}
    .summary {{ color: #cbd5e1; margin-bottom: 16px; }}
    audio {{ width: 100%; margin-bottom: 14px; }}
    details summary {{
      cursor: pointer;
      color: #a5b4fc;
      font-weight: 600;
      user-select: none;
    }}
    .transcript {{
      margin-top: 14px;
      border-top: 1px solid #334155;
      padding-top: 12px;
    }}
    .pair {{
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px dashed #334155;
    }}
    .zh {{ font-weight: 500; color: #f1f5f9; }}
    .en {{ color: #93c5fd; font-size: 0.96rem; margin-top: 2px; }}
    .num {{ color: var(--muted); margin-right: 4px; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <img src="cover.jpg" alt="Podcast Cover" />
      <div>
        <h1>{html.escape(title)}</h1>
        <p class="sub">{html.escape(subtitle)}</p>
        <div class="rss-box">
          <span>📡 Podcast RSS 訂閱網址：</span>
          <code>{html.escape(feed_url)}</code>
        </div>
      </div>
    </header>
    <main>
      {joined_cards}
    </main>
  </div>
</body>
</html>
"""
    (docs_dir / "index.html").write_text(index_html, encoding="utf-8")
