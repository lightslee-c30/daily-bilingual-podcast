import asyncio
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple
import urllib.request
from xml.sax.saxutils import escape
import edge_tts
import requests

logger = logging.getLogger(__name__)

# Edge-TTS & Azure Official REST API: MPEG-2 Layer III, 24000 Hz, 48 kbps, Mono (144 bytes / 24ms frame)
SILENT_FRAME_EDGE_24MS = b"\xff\xf3\x64\xc4" + (b"\x00" * 140)
# Google-TTS: MPEG-2 Layer III, 24000 Hz, 64 kbps, Mono (192 bytes / 24ms frame)
SILENT_FRAME_GOOGLE_24MS = b"\xff\xf3\x84\xc4" + (b"\x00" * 188)
FRAME_DURATION_MS = 24

# 使用者指定的聲音方案優先順序：方案4 ➔ 方案1 ➔ 方案5 ➔ 方案2 ➔ 方案6 ➔ 方案3
DEFAULT_PRESET_ORDER = [
    "preset_4",
    "preset_1",
    "preset_5",
    "preset_2",
    "preset_6",
    "preset_3",
]


def get_system_proxy() -> str | None:
    """自動偵測作業系統或環境變數中的 HTTP/HTTPS Proxy，確保 Edge-TTS 在公司或校園網路也能連線。"""
    proxies = urllib.request.getproxies()
    return (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or proxies.get("https")
        or proxies.get("http")
    )


def make_silence_mp3_bytes(duration_ms: int, engine: str = "edge") -> bytes:
    """產生指定毫秒數的無聲 MP3 二進位資料（無須依賴外部 ffmpeg）。"""
    if duration_ms <= 0:
        return b""
    num_frames = max(1, round(duration_ms / FRAME_DURATION_MS))
    frame = (
        SILENT_FRAME_EDGE_24MS
        if engine in ("edge", "azure")
        else SILENT_FRAME_GOOGLE_24MS
    )
    return frame * num_frames


def split_text_chunks(text: str, max_chars: int = 180) -> List[str]:
    """將長句切分為適合單次 TTS 請求的片段。"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts = re.split(r"(?<=[。！？.!?,，；;])\s*", text)
    chunks: List[str] = []
    current = ""
    for p in parts:
        if not p:
            continue
        if len(current) + len(p) <= max_chars:
            current += p
        else:
            if current:
                chunks.append(current)
            current = p
    if current:
        chunks.append(current)
    return chunks


def synthesize_azure_official_bytes(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> bytes:
    """
    【免費正版 API 通道】呼叫 Microsoft Azure AI Speech 官方 REST API (Free F0 方案每月免費 50 萬字元，具 100% 商用與公開發布授權)。
    輸出格式與 Edge-TTS 完全相同 (audio-24khz-48kbitrate-mono-mp3)。
    """
    azure_key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    azure_region = os.environ.get("AZURE_SPEECH_REGION", "eastasia").strip() or "eastasia"
    if not azure_key or azure_key == "your_azure_speech_key_here":
        raise RuntimeError("未設定有效的 AZURE_SPEECH_KEY")

    url = f"https://{azure_region}.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": azure_key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
        "User-Agent": "DailyBilingualPodcast/1.0",
    }
    xml_lang = "zh-TW" if voice.startswith("zh-") else "en-US"
    ssml = f"""<speak version='1.0' xml:lang='{xml_lang}'>
  <voice name='{escape(voice)}'>
    <prosody rate='{escape(rate)}' pitch='{escape(pitch)}'>{escape(text)}</prosody>
  </voice>
</speak>"""

    resp = requests.post(
        url,
        headers=headers,
        data=ssml.encode("utf-8"),
        timeout=20,
    )
    if resp.status_code != 200 or not resp.content:
        raise RuntimeError(
            f"Azure 官方 Speech API 呼叫失敗 (HTTP {resp.status_code}): {resp.text[:200]}"
        )
    return resp.content


def synthesize_google_tts_bytes(text: str, lang: str) -> bytes:
    """使用免費 Google Translate TTS 端點合成單句 MP3 (當未設定 Azure Key 且 Edge-TTS 無法連線時的緊急備援)。"""
    chunks = split_text_chunks(text, max_chars=180)
    out = bytearray()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for chunk in chunks:
        resp = requests.get(
            "https://translate.google.com/translate_tts",
            params={
                "ie": "UTF-8",
                "client": "tw-ob",
                "tl": lang,
                "q": chunk,
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200 or not resp.content:
            raise RuntimeError(
                f"Google TTS 請求失敗 (HTTP {resp.status_code}): {chunk[:30]}"
            )
        out.extend(resp.content)
    return bytes(out)


async def synthesize_edge_sentence_bytes(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    retries: int = 2,
) -> bytes:
    """呼叫微軟 Edge-TTS Neural 神經網路語音轉為 MP3 bytes（自動帶入系統 Proxy）。"""
    proxy = get_system_proxy()
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                pitch=pitch,
                proxy=proxy,
                connect_timeout=10,
                receive_timeout=20,
            )
            audio_chunks: List[bytes] = []
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    audio_chunks.append(chunk["data"])
            result = b"".join(audio_chunks)
            if result:
                return result
        except Exception as e:
            last_err = e
            logger.warning(f"Edge-TTS 合成重試 ({attempt}/{retries}) [{voice}]: {e}")
            await asyncio.sleep(1.0 * attempt)
    raise RuntimeError(f"無法透過 Edge-TTS 合成語音 [{voice}]: {last_err}")


def build_ordered_voice_candidates(
    tts_config: Dict[str, Any], is_zh: bool
) -> List[Tuple[str, str, str]]:
    """
    依照使用者喜好順序 (方案4 ➔ 方案1 ➔ 方案5 ➔ 方案2 ➔ 方案6 ➔ 方案3) 建立候選聲音清單。
    回傳 [(preset_name, voice, rate), ...]
    """
    presets = tts_config.get("presets", {})
    active_key = tts_config.get("active_preset", "preset_4")

    ordered_keys: List[str] = []
    if active_key in presets:
        ordered_keys.append(active_key)
    for k in DEFAULT_PRESET_ORDER:
        if k in presets and k not in ordered_keys:
            ordered_keys.append(k)

    candidates: List[Tuple[str, str, str]] = []
    seen_voices = set()

    for key in ordered_keys:
        p = presets[key]
        voice = p.get("zh_voice" if is_zh else "en_voice", "")
        rate = p.get("zh_rate" if is_zh else "en_rate", "+0%")
        name = p.get("name", key)
        if voice and (voice, rate) not in seen_voices:
            seen_voices.add((voice, rate))
            candidates.append((name, voice, rate))

    # 若 config 沒有 presets 區塊，則直接使用頂層設定
    if not candidates:
        voice = tts_config.get(
            "zh_voice" if is_zh else "en_voice",
            "en-US-AvaMultilingualNeural",
        )
        rate = tts_config.get("zh_rate" if is_zh else "en_rate", "+0%")
        candidates.append(("預設方案", voice, rate))

    return candidates


async def synthesize_with_fallback_chain(
    text: str,
    is_zh: bool,
    tts_config: Dict[str, Any],
    preferred_engine: str,
) -> Tuple[bytes, str]:
    """
    依照設定順序合成單句語音：
    1. 若 engine 為 "azure"，直接走微軟 Azure 官方正版免費 API。
    2. 若 engine 為 "auto" / "edge"：
       a) 依序嘗試使用者喜好的微軟 Neural 方案 (方案4 ➔ 方案1 ➔ 方案5 ➔ 方案2 ➔ 方案6 ➔ 方案3)
       b) 若 Edge-TTS 通道受阻，自動切換至最後備選「微軟 Azure 官方正版免費 API (AZURE_SPEECH_KEY)」
       c) 若尚未填寫 AZURE_SPEECH_KEY，才退回免費 Google TTS 確保不中斷。
    """
    candidates = build_ordered_voice_candidates(tts_config, is_zh=is_zh)
    primary_name, primary_voice, primary_rate = candidates[0]
    pitch = tts_config.get("zh_pitch" if is_zh else "en_pitch", "+0Hz")

    # 若明確指定使用官方正版 Azure API
    if preferred_engine == "azure":
        audio_bytes = synthesize_azure_official_bytes(
            text=text, voice=primary_voice, rate=primary_rate, pitch=pitch
        )
        return audio_bytes, "azure"

    # Step 1: 依使用者喜好順序 (方案4 -> 1 -> 5 -> 2 -> 6 -> 3) 嘗試 Edge-TTS
    if preferred_engine in ("auto", "edge"):
        for idx, (preset_name, voice, rate) in enumerate(candidates):
            try:
                if idx > 0:
                    logger.info(f"切換至下一順位喜好語音：{preset_name} ({voice})")
                audio_bytes = await synthesize_edge_sentence_bytes(
                    text=text, voice=voice, rate=rate, pitch=pitch
                )
                return audio_bytes, "edge"
            except Exception as e:
                logger.warning(f"方案 [{preset_name}] ({voice}) 無法合成: {e}")

    # Step 2: 最後備選方案 — 微軟 Azure 官方免費正版 API (AZURE_SPEECH_KEY)
    azure_key = os.environ.get("AZURE_SPEECH_KEY", "").strip()
    if azure_key and azure_key != "your_azure_speech_key_here":
        try:
            logger.info(
                f"啟用最後備選【微軟 Azure 官方免費正版 API 通道】({primary_voice})..."
            )
            audio_bytes = synthesize_azure_official_bytes(
                text=text, voice=primary_voice, rate=primary_rate, pitch=pitch
            )
            return audio_bytes, "azure"
        except Exception as e:
            logger.warning(f"Azure 官方正版 API 備援失敗: {e}")

    # Step 3: 若未設定 AZURE_SPEECH_KEY 的緊急保底備援
    logger.warning(
        "Edge-TTS 無法連線且未設定 AZURE_SPEECH_KEY，使用免費 Google TTS 緊急保底..."
    )
    lang = "zh-TW" if is_zh else "en"
    return synthesize_google_tts_bytes(text, lang=lang), "google"


async def generate_episode_audio_async(
    segments: List[Dict[str, str]],
    output_mp3_path: Path,
    tts_config: Dict[str, Any],
) -> Dict[str, Any]:
    """將所有「一句中文、再一句英文」段落依序合成並串接成單一 MP3 音檔。"""
    preferred_engine = tts_config.get("engine", "auto").lower()
    zh_candidates = build_ordered_voice_candidates(tts_config, is_zh=True)
    en_candidates = build_ordered_voice_candidates(tts_config, is_zh=False)

    proxy = get_system_proxy()
    logger.info(
        f"首選語音方案：{zh_candidates[0][0]} "
        f"(中文: {zh_candidates[0][1]}, 英文: {en_candidates[0][1]}"
        + (f", Proxy: {proxy})" if proxy else ")")
    )

    pause_between_ms = int(tts_config.get("pause_between_zh_and_en_ms", 350))
    pause_after_ms = int(tts_config.get("pause_after_pair_ms", 680))

    output_mp3_path.parent.mkdir(parents=True, exist_ok=True)
    combined_mp3 = bytearray()

    # 開頭先留 300ms 緩衝靜音
    combined_mp3.extend(make_silence_mp3_bytes(300, engine="edge"))

    used_engine = "edge"
    total = len(segments)
    for idx, seg in enumerate(segments, start=1):
        zh_text = (seg.get("zh") or "").strip()
        en_text = (seg.get("en") or "").strip()

        logger.info(f"正在合成雙語語音 ({idx}/{total}): {zh_text[:28]}...")

        if zh_text:
            zh_bytes, used_engine = await synthesize_with_fallback_chain(
                text=zh_text,
                is_zh=True,
                tts_config=tts_config,
                preferred_engine=preferred_engine,
            )
            combined_mp3.extend(zh_bytes)
            combined_mp3.extend(
                make_silence_mp3_bytes(pause_between_ms, engine=used_engine)
            )

        if en_text:
            en_bytes, used_engine = await synthesize_with_fallback_chain(
                text=en_text,
                is_zh=False,
                tts_config=tts_config,
                preferred_engine=preferred_engine,
            )
            combined_mp3.extend(en_bytes)
            combined_mp3.extend(
                make_silence_mp3_bytes(pause_after_ms, engine=used_engine)
            )

    try:
        output_mp3_path.write_bytes(bytes(combined_mp3))
        actual_path = output_mp3_path
    except PermissionError:
        alt_path = output_mp3_path.with_name(f"{output_mp3_path.stem}_updated.mp3")
        alt_path.write_bytes(bytes(combined_mp3))
        actual_path = alt_path
        logger.warning(
            f"原音檔 {output_mp3_path.name} 正被播放器開啟中，新音檔已另存為: {alt_path.name}"
        )

    file_size = actual_path.stat().st_size
    bytes_per_sec = 6000 if used_engine in ("edge", "azure") else 8000
    estimated_duration_sec = max(1, round(file_size / bytes_per_sec))

    logger.info(
        f"音檔合成完成: {actual_path} "
        f"(大小: {file_size / 1024:.1f} KB, 長度約: {estimated_duration_sec // 60}分{estimated_duration_sec % 60:02d}秒)"
    )

    return {
        "file_size": file_size,
        "duration_seconds": estimated_duration_sec,
    }


def generate_episode_audio(
    segments: List[Dict[str, str]],
    output_mp3_path: Path,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """同步包裝函式，產生雙語 Podcast MP3 音檔。"""
    tts_cfg = config.get("tts", {})
    return asyncio.run(
        generate_episode_audio_async(
            segments=segments,
            output_mp3_path=output_mp3_path,
            tts_config=tts_cfg,
        )
    )
