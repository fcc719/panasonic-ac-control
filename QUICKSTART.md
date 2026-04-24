# 📱 Panasonic IoT TW 遠端控制 - 快速開始指南

## ✅ 你現在已經有什麼

一個**完整的 FastAPI 後端**，可以：
- 🔐 登入 Panasonic IoT TW
- 📱 取得所有冷氣設備
- 🎛️ 遠端開/關冷氣
- 🌡️ 設定溫度
- 🚀 部署到 Railway（免費）

---

## 📦 文件說明

```
panasonic-backend/
├── main.py              ← 核心後端程式
├── requirements.txt     ← Python 依賴列表
├── README.md           ← 詳細文件
└── .gitignore          ← Git 忽略設定
```

---

## 🚀 部署到 Railway（3 步驟）

### 步驟 1️⃣：上傳到 GitHub

1. 在 GitHub 創建新倉庫，例如 `panasonic-ac-control`
2. 將 `panasonic-backend/` 中的所有檔案上傳到倉庫根目錄
3. 確保 `main.py` 和 `requirements.txt` 在根目錄

```bash
# 本地 Git 命令（如果你會用的話）
git clone https://github.com/你的用戶名/panasonic-ac-control.git
cd panasonic-ac-control
# 複製 main.py, requirements.txt 等檔案到這裡
git add .
git commit -m "Initial commit"
git push origin main
```

### 步驟 2️⃣：在 Railway 設定

1. 訪問 https://railway.app 並登入
2. 點擊「Create」→「New Project」
3. 選擇「Deploy from GitHub」
4. 授權 Railway 訪問你的 GitHub
5. 選擇 `panasonic-ac-control` 倉庫
6. Railway 會自動檢測並部署

### 步驟 3️⃣：設定環境變數

在 Railway 的「Variables」標籤中，添加：

```
PANASONIC_ACCOUNT = 你的 Panasonic 帳號 (Email 或手機號碼)
PANASONIC_PASSWORD = 你的 Panasonic 密碼
PORT = 8000
```

✅ Railway 會自動重新部署，完成！

---

## 📡 後端 API 端點

部署完成後，你會得到一個 URL，例如：
```
https://panasonic-ac-control-production.railway.app
```

### 基本使用

**1. 健康檢查**
```bash
curl https://panasonic-ac-control-production.railway.app/health
```

**2. 取得設備列表**
```bash
curl https://panasonic-ac-control-production.railway.app/api/devices
```

**3. 開啟冷氣**
```bash
curl -X POST \
  https://panasonic-ac-control-production.railway.app/api/devices/{device_id}/turn-on
```

**4. 設定溫度到 26°C**
```bash
curl -X POST \
  "https://panasonic-ac-control-production.railway.app/api/devices/{device_id}/set-temperature?temperature=26"
```

---

## 🎯 下一步：前端網頁

現在你有了後端，下一步是創建**手機網頁控制介面**，這會：
- 🎨 顯示所有冷氣設備
- 🔘 提供開/關按鈕
- 🌡️ 溫度調整滑塊
- 📱 在手機上優化顯示

前端可以部署到你現有的 **Cloudflare Pages**（靜態網站）。

---

## ⚙️ 本地測試（可選）

如果想在本地測試：

```bash
# 1. 安裝依賴
pip install -r requirements.txt

# 2. 創建 .env 文件
echo "PANASONIC_ACCOUNT=你的帳號" > .env
echo "PANASONIC_PASSWORD=你的密碼" >> .env
echo "PORT=8000" >> .env

# 3. 運行
python main.py

# 4. 訪問 API 文檔
# 打開瀏覽器: http://localhost:8000/docs
```

---

## 🔒 安全提醒

✅ **密碼不會存在程式碼中**
- 只存在 Railway 的環境變數中
- 環境變數被加密存儲
- GitHub 上看不到密碼

✅ **遠端訪問是安全的**
- 使用 HTTPS 加密
- Railway 提供 SSL 憑證

---

## 📋 檢查清單

完成部署時，確認：

- [ ] 在 GitHub 創建了倉庫
- [ ] 上傳了 `main.py` 和 `requirements.txt`
- [ ] 在 Railway 連接了 GitHub
- [ ] 設定了 `PANASONIC_ACCOUNT` 和 `PANASONIC_PASSWORD`
- [ ] Railway 顯示「Running」
- [ ] 能訪問後端 URL
- [ ] 可以成功調用 `/api/devices`

---

## 🆘 故障排除

### Railway 部署失敗

1. 檢查 GitHub 倉庫是否公開
2. 檢查 `main.py` 是否在根目錄
3. 檢查 `requirements.txt` 是否存在
4. 查看 Railway 的「Deployments」標籤看錯誤日誌

### 後端運行失敗

1. 檢查環境變數是否正確設定
2. 檢查 Panasonic 帳密是否正確
3. 檢查網路連線
4. 看日誌檔案了解詳細錯誤

### API 返回 401

- 帳號或密碼錯誤
- 需要重新登入

### 取不到設備列表

- 確認設備已在 Panasonic IoT TW app 中綁定
- 確認設備是否線上

---

## 📞 技術支援

查看 `README.md` 的「API 文檔」部分了解所有可用端點。

---

## 🎓 下一步：前端開發

當後端成功部署後，我們來做：

### 階段 3️⃣：手機網頁控制介面

將使用：
- HTML/CSS/JavaScript
- 調用你的後端 API
- 部署到 Cloudflare Pages

期待！ 🚀
