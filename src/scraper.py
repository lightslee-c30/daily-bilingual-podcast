import html
import logging
import re
import time
from typing import Any, Dict, List
import feedparser
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "windows:daily-bilingual-podcast:v1.0.0 (by /u/daily_bilingual_pod)"
}


def clean_html(raw_html: str) -> str:
    """移除 HTML 標籤並還原實體字元。"""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_top_comments(permalink_or_url: str, max_comments: int = 3) -> List[str]:
    """抓取 Reddit 文章底下的高讚熱門留言，支援 JSON 與 RSS 雙通道。"""
    if permalink_or_url.startswith("http"):
        base_post_url = permalink_or_url.rstrip("/")
    else:
        base_post_url = f"https://www.reddit.com{permalink_or_url}".rstrip("/")

    if not _REDDIT_JSON_BLOCKED:
        url = f"{base_post_url}.json?limit=10&sort=top"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) >= 2:
                    children = data[1].get("data", {}).get("children", [])
                    comments: List[str] = []
                    for child in children:
                        if child.get("kind") != "t1":
                            continue
                        c_data = child.get("data", {})
                        body = c_data.get("body", "").strip()
                        author = c_data.get("author", "")
                        if (
                            not body
                            or body in ("[deleted]", "[removed]")
                            or author == "AutoModerator"
                            or c_data.get("stickied", False)
                        ):
                            continue
                        if len(body) > 350:
                            body = body[:350] + "..."
                        comments.append(body)
                        if len(comments) >= max_comments:
                            break
                    if comments:
                        return comments
        except Exception as e:
            logger.debug(f"無法透過 JSON 抓取留言 ({base_post_url}): {e}")

    # RSS 留言通道備援 (.rss 第一筆是主文，第二筆開始是熱門留言)
    rss_url = f"{base_post_url}/.rss?limit={max_comments + 3}"
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
        comments = []
        for entry in feed.entries[1:]:
            author = entry.get("author", "")
            if "AutoModerator" in author:
                continue
            body = clean_html(entry.get("summary", "") or entry.get("content", [{}])[0].get("value", ""))
            if not body or body in ("[deleted]", "[removed]"):
                continue
            if len(body) > 350:
                body = body[:350] + "..."
            comments.append(body)
            if len(comments) >= max_comments:
                break
        return comments
    except Exception as e:
        logger.debug(f"無法透過 RSS 抓取留言 ({base_post_url}): {e}")
        return []


_REDDIT_JSON_BLOCKED = False


def fetch_subreddit_json(subreddit: str, limit: int = 5) -> List[Dict[str, Any]]:
    """透過 Reddit JSON API 抓取熱門文章，若失敗則回傳空陣列以便切換至 RSS 備援。"""
    global _REDDIT_JSON_BLOCKED
    if _REDDIT_JSON_BLOCKED:
        return []
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit={limit + 5}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            logger.info(
                f"Reddit JSON API 回傳 {resp.status_code}，自動切換為 Reddit RSS 通道抓取 r/{subreddit}..."
            )
            if resp.status_code in (403, 429):
                _REDDIT_JSON_BLOCKED = True
            return []
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        posts: List[Dict[str, Any]] = []
        for child in children:
            post = child.get("data", {})
            if post.get("stickied") or post.get("over_18"):
                continue
            title = post.get("title", "").strip()
            if not title:
                continue
            selftext = post.get("selftext", "").strip()
            if len(selftext) > 600:
                selftext = selftext[:600] + "..."
            permalink = post.get("permalink", "")
            score = post.get("score", 0)
            num_comments = post.get("num_comments", 0)

            posts.append(
                {
                    "source": f"Reddit r/{subreddit}",
                    "title": title,
                    "summary": selftext,
                    "url": f"https://www.reddit.com{permalink}" if permalink else post.get("url", ""),
                    "permalink": permalink,
                    "score": score,
                    "num_comments": num_comments,
                    "top_comments": [],
                }
            )
            if len(posts) >= limit:
                break
        return posts
    except Exception as e:
        logger.warning(f"抓取 Reddit JSON r/{subreddit} 發生錯誤: {e}")
        return []


def fetch_subreddit_rss(subreddit: str, limit: int = 5) -> List[Dict[str, Any]]:
    """當 Reddit JSON 被阻擋時，透過 Reddit RSS 抓取每日熱門文章。"""
    rss_url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day&limit={limit}"
    try:
        resp = requests.get(rss_url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
        posts: List[Dict[str, Any]] = []
        for idx, entry in enumerate(feed.entries[:limit]):
            title = entry.get("title", "").strip()
            if not title:
                continue
            summary = clean_html(entry.get("summary", ""))
            if len(summary) > 500:
                summary = summary[:500] + "..."
            link = entry.get("link", "")
            posts.append(
                {
                    "source": f"Reddit r/{subreddit}",
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "permalink": link,
                    "score": 1000 - idx * 50,
                    "num_comments": 200 - idx * 10,
                    "top_comments": [],
                }
            )
        return posts
    except Exception as e:
        logger.warning(f"抓取 Reddit RSS r/{subreddit} 發生錯誤: {e}")
        return []


def fetch_rss_feed(name: str, url: str, limit: int = 5) -> List[Dict[str, Any]]:
    """抓取一般新聞或 Hacker News RSS。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        feed = feedparser.parse(resp.text)
        items: List[Dict[str, Any]] = []
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            summary = clean_html(entry.get("summary", "") or entry.get("description", ""))
            if len(summary) > 500:
                summary = summary[:500] + "..."
            items.append(
                {
                    "source": name,
                    "title": title,
                    "summary": summary,
                    "url": entry.get("link", ""),
                    "permalink": "",
                    "score": 500,
                    "num_comments": 50,
                    "top_comments": [],
                }
            )
        return items
    except Exception as e:
        logger.warning(f"抓取 RSS {name} ({url}) 失敗: {e}")
        return []


def collect_daily_topics(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """整合設定檔中的所有 Reddit 看板與新聞 RSS，並針對最高討論度的文章抓取熱門留言。"""
    sources_cfg = config.get("sources", {})
    subreddits = sources_cfg.get("subreddits", [])
    rss_feeds = sources_cfg.get("rss_feeds", [])

    all_posts: List[Dict[str, Any]] = []

    for sub in subreddits:
        sub_name = sub.get("name")
        limit = int(sub.get("limit", 5))
        if not sub_name:
            continue
        logger.info(f"正在抓取 Reddit r/{sub_name} 熱門討論...")
        posts = fetch_subreddit_json(sub_name, limit=limit)
        if not posts:
            posts = fetch_subreddit_rss(sub_name, limit=limit)
        all_posts.extend(posts)
        time.sleep(0.8)

    # 依熱度 (score + 留言數權重) 排序，針對前 6 篇有 permalink 的 Reddit 文章抓取熱門留言
    all_posts.sort(
        key=lambda x: x.get("score", 0) + x.get("num_comments", 0) * 3,
        reverse=True,
    )

    comment_fetched = 0
    if not _REDDIT_JSON_BLOCKED:
        for post in all_posts:
            permalink = post.get("permalink")
            if permalink and comment_fetched < 6:
                post["top_comments"] = fetch_top_comments(permalink, max_comments=3)
                comment_fetched += 1
                time.sleep(0.5)

    # 同時抓取設定的 RSS 新聞做為補充或備援
    for rss in rss_feeds:
        name = rss.get("name", "News RSS")
        url = rss.get("url", "")
        if not url:
            continue
        logger.info(f"正在抓取新聞來源: {name}...")
        items = fetch_rss_feed(name, url, limit=5)
        all_posts.extend(items)

    logger.info(f"共蒐集到 {len(all_posts)} 則熱門文章與新聞。")
    return all_posts
