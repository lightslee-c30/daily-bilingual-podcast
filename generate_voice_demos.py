import asyncio
import html
from pathlib import Path
from src.audio_generator import generate_episode_audio_async

SAMPLE_SEGMENTS = [
    {
        "zh": "歡迎收聽今天的每日五分鐘雙語精華，我們一起用輕鬆的方式聽新聞、學英文。",
        "en": "Welcome to today's Five-Minute Bilingual Highlights, where we learn English effortlessly through trending stories.",
    },
    {
        "zh": "今天在 Reddit 的今日冷知識看板上，有一篇討論度破萬的熱門文章。",
        "en": "Today on Reddit's Today I Learned board, there is a viral post with tens of thousands of upvotes.",
    },
    {
        "zh": "科學家發現，海獺在睡覺的時候會手牽著手，這樣才不會被海浪沖散。",
        "en": "Scientists found that sea otters hold hands while sleeping so they don't drift apart in the current.",
    },
    {
        "zh": "底下有網友幽默地留言說，連海獺都有人牽手，看來我比海獺還孤單。",
        "en": "One top commenter joked, even sea otters have someone to hold hands with, I guess I am lonelier than an otter.",
    },
]

DEMO_CONFIGS = [
    {
        "id": "demo_1_tw_hsiaochen_ava",
        "title": "方案 1：台灣溫暖女聲（曉臻）＋ 美國擬真女聲（Ava）",
        "badge": "🔥 最推薦・台灣自然口音",
        "desc": "台灣最受歡迎的親切女聲 zh-TW-HsiaoChenNeural，搭配微軟最新世代超自然美語女聲 en-US-AvaMultilingualNeural。",
        "tts": {
            "zh_voice": "zh-TW-HsiaoChenNeural",
            "zh_rate": "+2%",
            "en_voice": "en-US-AvaMultilingualNeural",
            "en_rate": "-4%",
            "pause_between_zh_and_en_ms": 380,
            "pause_after_pair_ms": 700,
        },
    },
    {
        "id": "demo_2_yunxi_andrew",
        "title": "方案 2：陽光磁性男聲（雲希）＋ 美國電台男聲（Andrew）",
        "badge": "🎙️ 沉穩電台男主持風",
        "desc": "微軟最受歡迎的青年男聲 zh-CN-YunxiNeural，搭配極具 Podcast 聊天感的美式低沉男聲 en-US-AndrewMultilingualNeural。",
        "tts": {
            "zh_voice": "zh-CN-YunxiNeural",
            "zh_rate": "+0%",
            "en_voice": "en-US-AndrewMultilingualNeural",
            "en_rate": "-4%",
            "pause_between_zh_and_en_ms": 380,
            "pause_after_pair_ms": 700,
        },
    },
    {
        "id": "demo_3_tw_hsiaoyu_emma",
        "title": "方案 3：台灣輕快女聲（曉雨）＋ 美國活力女聲（Emma）",
        "badge": "✨ 晨間新聞輕快風",
        "desc": "節奏明快有朝氣的台灣女聲 zh-TW-HsiaoYuNeural，搭配清晰口語化的 en-US-EmmaMultilingualNeural，適合早上通勤提神。",
        "tts": {
            "zh_voice": "zh-TW-HsiaoYuNeural",
            "zh_rate": "+0%",
            "en_voice": "en-US-EmmaMultilingualNeural",
            "en_rate": "-4%",
            "pause_between_zh_and_en_ms": 380,
            "pause_after_pair_ms": 700,
        },
    },
    {
        "id": "demo_4_ava_multilingual_single",
        "title": "方案 4：同一位超擬真女聲包辦中英（Ava Multilingual）",
        "badge": "🌟 最新世代多語模型（中英不換人）",
        "desc": "中英文皆使用 en-US-AvaMultilingualNeural，具有真人呼吸感與自然抑揚頓挫，且中英切換時完全是同一個人的聲音（帶微ABC腔調）。",
        "tts": {
            "zh_voice": "en-US-AvaMultilingualNeural",
            "zh_rate": "+0%",
            "en_voice": "en-US-AvaMultilingualNeural",
            "en_rate": "-4%",
            "pause_between_zh_and_en_ms": 350,
            "pause_after_pair_ms": 680,
        },
    },
    {
        "id": "demo_5_andrew_multilingual_single",
        "title": "方案 5：同一位超擬真男聲包辦中英（Andrew Multilingual）",
        "badge": "🎧 美式 Podcast 雙語男主持（中英不換人）",
        "desc": "中英文皆使用 en-US-AndrewMultilingualNeural，語氣非常像真人在錄音室裡對著麥克風跟你聊天，中英轉換毫無違和感。",
        "tts": {
            "zh_voice": "en-US-AndrewMultilingualNeural",
            "zh_rate": "+0%",
            "en_voice": "en-US-AndrewMultilingualNeural",
            "en_rate": "-4%",
            "pause_between_zh_and_en_ms": 350,
            "pause_after_pair_ms": 680,
        },
    },
    {
        "id": "demo_6_xiaoxiao_jenny",
        "title": "方案 6：高情感說書女聲（曉曉）＋ 柔和美語（Jenny）",
        "badge": "🎭 抑揚頓挫最強",
        "desc": "微軟情緒起伏最豐富的中文神經網路女聲 zh-CN-XiaoxiaoNeural（字正腔圓說書腔），搭配柔和美語 en-US-JennyNeural。",
        "tts": {
            "zh_voice": "zh-CN-XiaoxiaoNeural",
            "zh_rate": "+0%",
            "en_voice": "en-US-JennyNeural",
            "en_rate": "-4%",
            "pause_between_zh_and_en_ms": 380,
            "pause_after_pair_ms": 700,
        },
    },
]


async def main() -> None:
    root = Path(__file__).resolve().parent
    demos_dir = root / "docs" / "demos"
    demos_dir.mkdir(parents=True, exist_ok=True)

    cards_html = []
    for item in DEMO_CONFIGS:
        mp3_name = f"{item['id']}.mp3"
        mp3_path = demos_dir / mp3_name
        if not mp3_path.exists():
            print(f"正在產生試聽音檔: {item['title']} -> {mp3_path.name}")
            await generate_episode_audio_async(
                segments=SAMPLE_SEGMENTS,
                output_mp3_path=mp3_path,
                tts_config=item["tts"],
            )

        zh_v = item["tts"]["zh_voice"]
        en_v = item["tts"]["en_voice"]
        cards_html.append(
            f"""
            <div class="card">
              <div class="badge">{html.escape(item['badge'])}</div>
              <h2>{html.escape(item['title'])}</h2>
              <p class="desc">{html.escape(item['desc'])}</p>
              <audio controls src="demos/{mp3_name}"></audio>
              <div class="cfg">
                <span><code>config.yaml</code> 設定值：</span>
                <code>zh_voice: "{zh_v}"</code> | <code>en_voice: "{en_v}"</code>
              </div>
            </div>
            """
        )

    html_page = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>🎙️ 免費 AI 雙語語音 Demo 試聽比較</title>
  <style>
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f172a;
      color: #f8fafc;
      line-height: 1.6;
    }}
    .container {{ max-width: 860px; margin: 0 auto; padding: 36px 20px; }}
    h1 {{ margin-top: 0; font-size: 1.8rem; }}
    .intro {{
      background: #1e293b;
      border-left: 4px solid #6366f1;
      padding: 16px 20px;
      border-radius: 10px;
      margin-bottom: 28px;
      color: #cbd5e1;
    }}
    .card {{
      background: #1e293b;
      border-radius: 16px;
      padding: 22px 24px;
      margin-bottom: 20px;
      border: 1px solid #334155;
    }}
    .badge {{
      display: inline-block;
      background: rgba(99, 102, 241, 0.2);
      color: #a5b4fc;
      font-size: 0.82rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
      margin-bottom: 8px;
    }}
    h2 {{ margin: 0 0 8px 0; font-size: 1.25rem; color: #fff; }}
    .desc {{ margin: 0 0 14px 0; color: #cbd5e1; font-size: 0.95rem; }}
    audio {{ width: 100%; margin-bottom: 10px; }}
    .cfg {{
      font-size: 0.85rem;
      color: #94a3b8;
      background: #0f172a;
      padding: 8px 12px;
      border-radius: 8px;
    }}
    code {{ color: #93c5fd; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>🎧 6 組免費 AI 雙語語音 Demo 試聽比較</h1>
    <div class="intro">
      💡 <strong>為什麼剛才第一版聽起來比較生硬？</strong><br/>
      因為你的網路環境有設定系統 Proxy（<code>10.160.3.88:8080</code>），剛才第一版未帶入 Proxy 導致微軟神經網路語音連線逾時，程式自動退回使用了舊版 Google 翻譯機械音。<br/>
      現在已經自動接通你的系統 Proxy，以下 <strong>6 組全都是完全免費的微軟 Neural 與最新 Multilingual 超擬真神經網路語音</strong>，請直接點擊播放試聽比較！
    </div>
    {''.join(cards_html)}
  </div>
</body>
</html>
"""
    out_html = root / "docs" / "voice_demos.html"
    out_html.write_text(html_page, encoding="utf-8")
    print(f"試聽比較頁面已產生: {out_html}")


if __name__ == "__main__":
    asyncio.run(main())
