# 🎙️ Daily Bilingual Podcast (Reddit & 新聞每日五分鐘雙語精華)

自動從 **Reddit 熱門看板**（`r/todayilearned`, `r/worldnews`, `r/technology`, `r/UpliftingNews`, `r/science`）與國際新聞 RSS 蒐集每日高討論度話題，透過 **Google Gemini API** 整理成約 **5 分鐘** 的雙語廣播講稿，並使用免費自然的 **Microsoft Edge TTS** 以 **「一句中文、再一句英文」** 交替朗讀合成 `.mp3` 音檔，最後透過 **GitHub Pages + GitHub Actions** 每日自動更新發佈至 **Spotify / Apple Podcasts**！

---

## ✨ 專案架構與特色

```
daily-bilingual-podcast/
├── config.yaml                         # 看板來源、語音聲優、語速與頻道設定檔
├── main.py                             # 主程式：一鍵完成爬蟲 → 雙語講稿 → 音檔合成 → RSS 更新
├── requirements.txt                    # Python 套件清單
├── .env.example                        # 環境變數範本 (GEMINI_API_KEY)
├── src/
│   ├── scraper.py                      # 抓取 Reddit 熱門文章、高讚鄉民留言與 RSS 備援
│   ├── script_generator.py             # Gemini 結構化雙語講稿生成 (一句中文對應一句英文)
│   ├── audio_generator.py              # Edge-TTS 雙語音色交替合成 + 句間自然停頓 (免裝 ffmpeg)
│   └── feed_generator.py               # 自動產出符合 Apple/Spotify 規範的 feed.xml、封面圖與線上播放器網頁
├── docs/                               # GitHub Pages 靜態託管目錄 (自動生成)
│   ├── cover.jpg                       # 1400x1400 頻道封面圖
│   ├── feed.xml                        # Podcast RSS 訂閱源 (提交給 Spotify / Apple Podcasts)
│   ├── index.html                      # 網頁版播放器 + 中英對照逐字稿
│   └── episodes/                       # 每日單集 MP3 音檔與 JSON 逐字稿
└── .github/workflows/
    └── daily_podcast.yml               # GitHub Actions 每日定時排程 (預設每天台灣時間 07:00)
```

---

## 🚀 第一步：在本機測試執行

1. **建立虛擬環境並安裝依賴套件**
   ```powershell
   cd i:\backupC\app\daily-bilingual-podcast
   py -3.12 -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```

2. **先用 `--demo` 示範模式測試語音合成與 RSS（免 API Key）**
   ```powershell
   .\.venv\Scripts\python main.py --demo --force
   ```
   執行完成後，可以在 `docs/episodes/` 聽聽看產出的雙語 MP3 音檔，或直接用瀏覽器打開 `docs/index.html`！

3. **設定真實的 Gemini API Key 並正式執行**
   - 前往 [Google AI Studio](https://aistudio.google.com/app/apikey) 免費取得一組 API Key。
   - 複製 `.env.example` 為 `.env`，填入你的 `GEMINI_API_KEY`：
     ```env
     GEMINI_API_KEY=AIzaSyYourKeyHere...
     ```
   - 執行正式抓取與生成：
     ```powershell
     python main.py --force
     ```

---

## ☁️ 第二步：部署到 GitHub 實現「每日全自動更新」

1. **建立新的 GitHub Repository**
   - 前往 GitHub 建立一個 **Public（公開）** 的 Repository，例如命名為 `daily-bilingual-podcast`。
   - 將 `daily-bilingual-podcast` 資料夾內的檔案推送上去：
     ```powershell
     git init
     git add .
     git commit -m "Initial commit: daily bilingual podcast"
     git branch -M main
     git remote add origin https://github.com/<你的GitHub帳號>/daily-bilingual-podcast.git
     git push -u origin main
     ```

2. **設定 GitHub Secrets**
   - 進入你的 GitHub Repo 頁面 → **Settings** → 左側 **Secrets and variables** → **Actions**。
   - 點擊 **New repository secret**，新增以下兩個 Secret：
     - `GEMINI_API_KEY`：填入你的 Google Gemini API Key。
     - `PODCAST_EMAIL`：填入你的個人常用 Email（稍後 Spotify / Apple 驗證頻道擁有權時會寄驗證碼或確認信到這個信箱，也會寫入 `feed.xml` 的 `<itunes:email>`）。

3. **開啟 GitHub Pages 託管音檔與 RSS**
   - 進入 GitHub Repo → **Settings** → 左側 **Pages**。
   - 在 **Build and deployment** 下方：
     - **Source** 選擇 `Deploy from a branch`
     - **Branch** 選擇 `main`，資料夾選擇 `/docs`，點擊 **Save**。
   - 等待約 1～2 分鐘後，你的專屬網站與 RSS Feed 就會上線：
     - 網頁版收聽：`https://<你的GitHub帳號>.github.io/daily-bilingual-podcast/`
     - **Podcast RSS 網址**：`https://<你的GitHub帳號>.github.io/daily-bilingual-podcast/feed.xml`

4. **手動觸發第一次自動排程**
   - 進入 GitHub Repo 上方的 **Actions** 頁籤 → 點選左側 **Daily Bilingual Podcast Generator** → 點擊右側 **Run workflow**。
   - 之後每天台灣時間早上 07:00，GitHub Actions 就會自動抓新聞、寫雙語稿、合成 MP3 並更新 `feed.xml`！

---

## 🎧 第三步：免費建立你的 Podcast 頻道（上架 Spotify / Apple Podcasts）

因為 Podcast 的運作機制是「各平台自動去讀取你的 `feed.xml`」，所以你**只需要在第一次建立頻道時綁定一次 RSS 網址**，之後每天 GitHub Actions 更新 `feed.xml`，所有平台就會自動同步發布新單集！

### 1. 上架至 Spotify（完全免費，審核最快）
1. 前往 [Spotify for Creators (原 Anchor)](https://creators.spotify.com/) 並用你的 Spotify 帳號登入。
2. 點選 **「我已經有 Podcast (I have a podcast)」** 或 **「新增現有節目 (Add an existing podcast / RSS feed)」**。
3. 貼上你的 GitHub Pages RSS 網址：
   `https://<你的GitHub帳號>.github.io/daily-bilingual-podcast/feed.xml`
4. 系統會寄一封驗證碼到你在 `PODCAST_EMAIL`（或 `config.yaml` 的 `email`）設定的信箱，輸入驗證碼後即可完成提交！通常數小時內就能在 Spotify 搜尋到你的節目。

### 2. 上架至 Apple Podcasts / Pocket Casts / KKBOX
- **Apple Podcasts**：前往 [Apple Podcasts Connect](https://podcastsconnect.apple.com/) 登入 Apple ID → 點擊「`+`」→ **Add a Show** → 選擇 **Add a show with an RSS feed** → 貼上同一個 `feed.xml` 網址即可。
- **Firstory / KKBOX**：前往各自創作者後台選擇「透過 RSS 匯入節目」，貼上同一個 `feed.xml` 網址即可同步上架。
- **個人搶先收聽**：在手機的 **Apple Podcasts** 或 **Pocket Casts** App 中，點選「透過網址追蹤節目 (Follow a Show by URL)」，直接貼上 `feed.xml` 網址，不用等審核就能馬上在手機收聽！
