from datetime import datetime
import json
import logging
import os
from typing import Any, Dict, List
import requests

logger = logging.getLogger(__name__)


def build_prompt(
    topics: List[Dict[str, Any]],
    date_str: str,
    stories_count: int = 3,
    target_pairs: int = 30,
) -> str:
    """組合提供給 Gemini 的提示詞，要求產出約 5 分鐘的「一句中文、一句英文」Podcast 講稿。"""
    candidates_text = []
    for idx, item in enumerate(topics[:18], start=1):
        comments_str = ""
        if item.get("top_comments"):
            joined_comments = " | ".join(item["top_comments"])
            comments_str = f"\n   熱門網友留言: {joined_comments}"
        candidates_text.append(
            f"[{idx}] 來源: {item.get('source')}\n"
            f"   標題: {item.get('title')}\n"
            f"   熱度: {item.get('score')} 讚 / {item.get('num_comments')} 則留言\n"
            f"   內容摘要: {item.get('summary') or '(僅標題)'}"
            f"{comments_str}\n"
            f"   連結: {item.get('url')}"
        )

    joined_candidates = "\n\n".join(candidates_text)

    return f"""你是一位風趣、口語自然的中英雙語 Podcast 主持人。
今天日期是 {date_str}。請從以下今日蒐集到的 Reddit 熱門討論與國際新聞清單中，挑選最有趣、最有話題性或最能引發思考的 {stories_count} 則主題，編寫成一集約 5 分鐘的雙語 Podcast 節目講稿。

【節目核心規則：一句中文、再一句英文】
1. 整集講稿由多個「句子對 (segments)」組成，每個 segment 包含：
   - `"zh"`: 一句自然的繁體中文（台灣習慣用語，口語化、適合直接朗讀，長度約 20～45 字）。
   - `"en"`: 對應同一句意思的自然道地英文（長度約 12～28 個英文單字，適合英語學習者邊聽邊吸收）。
2. 請確保每一句 `"zh"` 與 `"en"` 語意彼此對應，因為系統會先用中文語音唸完 `"zh"`，接著立刻用英文語音唸出 `"en"`！
3. 總共請產出約 {target_pairs} 組句子對（範圍 26～34 組），這樣中英交替朗讀加上停頓剛好約 5 分鐘。
4. 內容結構：
   - 開場白（約 2～3 組）：歡迎聽眾收聽今天的每日五分鐘雙語精華，預告今天挑選的亮點。
   - 主題一～主題{stories_count}（每個主題約 8～9 組）：生動介紹事件背景、為什麼這件事很有趣，以及 **Reddit 網友們在留言區最爆笑或最犀利的反應**。
   - 結尾（約 2 組）：總結今日重點，祝聽眾有美好的一天並提醒訂閱頻道。
5. 注意事項：
   - 嚴禁在 `"zh"` 或 `"en"` 句子中出現 Markdown 符號（如 `*`, `#`, `-`）、括號註解或網址，所有數字與縮寫請寫成適合語音合成 (TTS) 直接唸出來的文字。
   - `"zh"` 內請勿夾雜英文單字（專有名詞可音譯或直接用中文表達），讓中文語音引擎發音純粹自然；英文則放在 `"en"`。

請嚴格輸出符合以下格式的 JSON 物件：
{{
  "episode_title": "今日雙語精華：...(吸引人的中英或中文標題)",
  "episode_summary": "本集收錄：1. ... 2. ... 3. ... (約 100 字內的節目簡介，會顯示在 Podcast App 中)",
  "selected_links": [
    {{"title": "原文標題", "url": "https://..."}}
  ],
  "segments": [
    {{
      "zh": "歡迎收聽今天的每日五分鐘雙語新聞與 Reddit 熱門精華。",
      "en": "Welcome to today's five-minute bilingual news and Reddit highlights."
    }}
  ]
}}

【今日候選熱門話題與新聞清單】：
{joined_candidates}
"""


def generate_bilingual_script(
    topics: List[Dict[str, Any]],
    config: Dict[str, Any],
    date_str: str | None = None,
    use_demo: bool = False,
) -> Dict[str, Any]:
    """呼叫 Gemini REST API 產生結構化雙語講稿；若指定 use_demo 則回傳範例講稿供測試。"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    if use_demo:
        logger.info("使用內建範例雙語講稿 (--demo 模式)...")
        return get_demo_script(date_str)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        raise ValueError(
            "找不到有效的 GEMINI_API_KEY！請先在 .env 檔案或環境變數中設定 GEMINI_API_KEY，"
            "或加上 --demo 參數執行測試模式。"
        )

    script_cfg = config.get("script", {})
    model_name = script_cfg.get("model", "gemini-2.5-flash")
    stories_count = int(script_cfg.get("stories_per_episode", 3))
    target_pairs = int(script_cfg.get("target_sentence_pairs", 30))

    prompt = build_prompt(
        topics=topics,
        date_str=date_str,
        stories_count=stories_count,
        target_pairs=target_pairs,
    )

    logger.info(f"正在使用 Gemini ({model_name}) 撰寫中英對照 Podcast 講稿...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.7,
        },
    }
    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key},
        json=payload,
        timeout=90,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Gemini API 呼叫失敗 (HTTP {resp.status_code}): {resp.text[:400]}"
        )

    resp_json = resp.json()
    try:
        raw_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"無法解析 Gemini 回應結構: {resp_json}") from e

    data = json.loads(raw_text)

    segments = data.get("segments", [])
    if not segments:
        raise RuntimeError("Gemini 回傳的講稿中沒有 segments 內容！")

    logger.info(
        f"成功產生講稿：《{data.get('episode_title')}》，共 {len(segments)} 組中英對照句子。"
    )
    return data


def get_demo_script(date_str: str) -> Dict[str, Any]:
    """提供無須 API Key 即可測試整套音檔合成與 RSS 流程的示範講稿。"""
    return {
        "episode_title": f"【示範集】Reddit 每日五分鐘雙語精華 ({date_str})",
        "episode_summary": "本集為系統測試示範集：透過一句中文、再一句英文的方式，帶你速覽 Reddit 熱門冷知識與科技話題。",
        "selected_links": [
            {
                "title": "Reddit r/todayilearned & r/technology Highlights",
                "url": "https://www.reddit.com/r/todayilearned/",
            }
        ],
        "segments": [
            {
                "zh": "歡迎收聽每日五分鐘雙語精華，一起用輕鬆的方式聽新聞學英文。",
                "en": "Welcome to the Daily Five-Minute Bilingual Highlights, where we learn English effortlessly through trending stories.",
            },
            {
                "zh": "今天我們從 Reddit 上挑選了幾個討論度極高的有趣話題。",
                "en": "Today we have handpicked several fascinating topics that are trending heavily on Reddit.",
            },
            {
                "zh": "首先在今日冷知識看板上，有網友分享了一個關於海洋生物的驚人發現。",
                "en": "First up on the Today I Learned board, a user shared an amazing discovery about marine life.",
            },
            {
                "zh": "科學家發現，章魚其實擁有三個心臟，而且牠們的血液是藍色的。",
                "en": "Scientists found that octopuses actually have three hearts, and their blood is blue.",
            },
            {
                "zh": "留言區的網友幽默地表示，難怪章魚面對壓力時比人類還要冷靜。",
                "en": "Commenters joked that this explains why octopuses stay much calmer under pressure than humans do.",
            },
            {
                "zh": "接著在科技看板上，大家正熱烈討論人工智慧語音技術的最新進展。",
                "en": "Next on the technology board, people are actively discussing the latest breakthroughs in artificial intelligence voice synthesis.",
            },
            {
                "zh": "現在我們只需要簡單的腳本，就能每天自動把全球趣聞轉換成雙語廣播節目。",
                "en": "Now with just a simple script, we can automatically turn global stories into a daily bilingual podcast.",
            },
            {
                "zh": "以上就是今天的示範內容，感謝你的收聽，我們明天見！",
                "en": "That wraps up today's demo episode, thank you for listening, and see you tomorrow!",
            },
        ],
    }
