# Panasonic IoT TW 遠端控制後端

基於開源專案 `osk2/panasonic_smart_app` 改造，用 FastAPI 實現的 Panasonic IoT TW 冷氣遠端控制後端。

## 功能

- ✅ 登入 Panasonic IoT TW
- ✅ 取得所有已註冊的冷氣設備列表
- ✅ 開/關冷氣
- ✅ 設定溫度
- ✅ 設定運行模式
- ✅ RESTful API 接口

## 部署到 Railway

### 步驟 1: 準備 GitHub 倉庫

1. 在 GitHub 創建新倉庫 (例如 `panasonic-ac-control`)
2. 上傳以下檔案:
   - `main.py` - FastAPI 主程序
   - `requirements.txt` - Python 依賴

### 步驟 2: 連接 Railway

1. 訪問 https://railway.app
2. 登入/註冊賬號
3. 創建新 Project
4. 選擇 "Deploy from GitHub"
5. 連接你的 GitHub 倉庫
6. 選擇分支 (通常是 `main`)

### 步驟 3: 設定環境變數

在 Railway 項目中設定以下環境變數:

```
PANASONIC_ACCOUNT=你的Panasonic帳號 (Email或手機號碼)
PANASONIC_PASSWORD=你的密碼
PORT=8000
```

> ⚠️ **安全提醒**: 環境變數在 Railway 中是加密存儲的，不會暴露在程式碼中

### 步驟 4: 自動部署

一旦設定好環境變數，Railway 會自動:
1. 檢出你的代碼
2. 安裝 `requirements.txt` 中的依賴
3. 運行 `main.py`

### 步驟 5: 獲取公開 URL

部署完成後，Railway 會給你一個公開 URL，例如:
```
https://panasonic-ac-control-production.railway.app
```

## 本地測試

### 安裝依賴

```bash
pip install -r requirements.txt
```

### 設定環境變數

創建 `.env` 檔案:
```
PANASONIC_ACCOUNT=你的帳號
PANASONIC_PASSWORD=你的密碼
PORT=8000
```

### 運行後端

```bash
python main.py
```

訪問 http://localhost:8000/docs 查看 API 文件

## API 文檔

### 1. 健康檢查

```
GET /health
```

響應:
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T12:00:00"
}
```

### 2. 登入

```
POST /api/login
Content-Type: application/json

{
  "account": "你的帳號",
  "password": "你的密碼"
}
```

### 3. 取得設備列表

```
GET /api/devices
```

響應:
```json
{
  "devices": [
    {
      "id": "GWID_123",
      "name": "主臥 冷氣",
      "auth": "Auth_ID",
      "gwid": "GWID_123",
      "device_type": 0,
      "is_online": true,
      "model": "CS-RX22NA2"
    }
  ],
  "count": 1
}
```

### 4. 開啟冷氣

```
POST /api/devices/{device_id}/turn-on
```

### 5. 關閉冷氣

```
POST /api/devices/{device_id}/turn-off
```

### 6. 設定溫度

```
POST /api/devices/{device_id}/set-temperature?temperature=26.0
```

### 7. 發送自訂命令

```
POST /api/devices/{device_id}/command
Content-Type: application/json

{
  "device_id": "GWID_123",
  "command_type": "0x04",
  "value": 52
}
```

## 命令類型參考

| 命令類型 | 說明 | 值 |
|---------|------|-----|
| 0x00 | 開/關 | 0=關, 1=開 |
| 0x01 | 運行模式 | 0=冷氣, 1=除濕, 2=通風, 3=暖氣 |
| 0x04 | 設定溫度 | 16-32°C (以 0.5°C 為單位，值 = 溫度 × 2) |
| 0x06 | 風速 | 0=自動, 1=低, 2=中, 3=高 |
| 0x07 | 左右搖擺 | 0=關, 1=開 |
| 0x08 | 上下搖擺 | 0=關, 1=開 |

## 故障排除

### 登入失敗

- 確認帳號是否正確 (Email 或手機號碼都可以)
- 確認密碼是否正確
- 檢查 Panasonic IoT TW app 是否能正常登入

### 無法取得設備列表

- 確認已登入
- 檢查設備是否在 Panasonic IoT TW app 中已綁定
- 檢查網路連線

### 命令發送失敗

- 確認設備是否線上
- 檢查命令類型和值是否正確
- 查看日誌了解詳細錯誤信息

## 原始碼信息

本程序基於以下開源專案:
- GitHub: https://github.com/osk2/panasonic_smart_app
- License: MIT

核心 API 邏輯來自該專案，用 FastAPI 改造並簡化了部分實現。
