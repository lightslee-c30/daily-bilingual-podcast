import argparse
from datetime import datetime, timezone
from email.utils import format_datetime
import json
import logging
from pathlib import Path
import sys
from dotenv import load_dotenv
import yaml

from src.audio_generator import generate_episode_audio
from src.feed_generator import update_feed_and_website
from src.scraper import collect_daily_topics
from src.script_generator import generate_bilingual_script


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    setup_logging()
    logger = logging.getLogger("main")

    parser = argparse.ArgumentParser(
        description="每日自動蒐集 Reddit / 新聞並產出中英雙語 Podcast 音檔與 RSS Feed"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="設定檔路徑 (預設: config.yaml)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="指定單集日期 YYYY-MM-DD (預設為今天)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="使用內建示範講稿測試音檔合成與 RSS 產生 (無須 GEMINI_API_KEY)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="若當日音檔已存在，強制重新產生",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")

    config_path = project_root / args.config
    if not config_path.exists():
        logger.error(f"找不到設定檔: {config_path}")
        return 1

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    docs_dir = project_root / "docs"
    episodes_dir = docs_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=True)

    date_str = args.date
    mp3_filename = f"{date_str}.mp3"
    mp3_path = episodes_dir / mp3_filename
    json_path = episodes_dir / f"{date_str}.json"

    if mp3_path.exists() and json_path.exists() and not args.force:
        logger.info(
            f"今日 ({date_str}) 的單集音檔已存在: {mp3_path}。僅更新 RSS Feed 與網頁 (若需重產請加 --force)。"
        )
        update_feed_and_website(docs_dir=docs_dir, config=config)
        return 0

    # Step 1: 抓取 Reddit 熱門話題與新聞
    if args.demo:
        topics = []
    else:
        topics = collect_daily_topics(config)
        if not topics:
            logger.error("未能抓取到任何熱門文章或新聞，請檢查網路連線。")
            return 1

    # Step 2: 產生「一句中文、一句英文」雙語講稿
    script_data = generate_bilingual_script(
        topics=topics,
        config=config,
        date_str=date_str,
        use_demo=args.demo,
    )

    # Step 3: 透過 Edge-TTS 合成雙語交替 MP3 音檔
    audio_stats = generate_episode_audio(
        segments=script_data["segments"],
        output_mp3_path=mp3_path,
        config=config,
    )

    # Step 4: 儲存單集資訊與逐字稿 JSON
    episode_record = {
        "date": date_str,
        "episode_title": script_data.get("episode_title", f"Daily Bilingual ({date_str})"),
        "episode_summary": script_data.get("episode_summary", ""),
        "selected_links": script_data.get("selected_links", []),
        "segments": script_data.get("segments", []),
        "mp3_filename": mp3_filename,
        "file_size": audio_stats["file_size"],
        "duration_seconds": audio_stats["duration_seconds"],
        "pub_date_rfc2822": format_datetime(datetime.now(timezone.utc)),
    }
    json_path.write_text(
        json.dumps(episode_record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Step 5: 更新 Podcast RSS Feed (docs/feed.xml) 與首頁 (docs/index.html)
    feed_path = update_feed_and_website(docs_dir=docs_dir, config=config)

    logger.info("====================================================")
    logger.info(f"🎉 今日雙語 Podcast 單集製作完成！")
    logger.info(f"🎧 音檔位置: {mp3_path}")
    logger.info(f"📝 逐字稿與資訊: {json_path}")
    logger.info(f"📡 RSS Feed: {feed_path}")
    logger.info(f"🌐 網頁預覽: {docs_dir / 'index.html'}")
    logger.info("====================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
