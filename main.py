"""
Panasonic IoT TW FastAPI 後端
包含即時狀態查詢與前端相容 API
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import os
from datetime import datetime
import json
import urllib.request
import urllib.error

# 配置日誌
logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

# ============================================================================
# 常數定義
# ============================================================================

BASE_URL = "https://ems2.panasonic.com.tw/api"
APP_TOKEN = "D8CBFF4C-2824-4342-B22D-189166FEF503"
USER_AGENT = "okhttp/4.9.1"

# ============================================================================
# 自訂例外
# ============================================================================

class PanasonicException(Exception): pass
class PanasonicLoginFailed(PanasonicException): pass

# ============================================================================
# API URLs
# ============================================================================

def api_login(): return f"{BASE_URL}/userlogin1"
def api_get_devices(): return f"{BASE_URL}/UserGetRegisteredGwList2"
def api_get_device_info(): return f"{BASE_URL}/DeviceGetInfo"
def api_set_command(): return f"{BASE_URL}/DeviceSetCommand"
def api_refresh_token(): return f"{BASE_URL}/RefreshToken1"

# ============================================================================
# Panasonic Smart App API 客戶端
# ============================================================================

class PanasonicSmartApp:
    def __init__(self, account: str, password: str):
        self.account = account
        self.password = password
        self._cp_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._devices: List[Dict] = []
    
    def _request(self, method: str, endpoint: str, headers: Dict = None, data: Dict = None, params: Dict = None) -> Dict:
        if headers is None: headers = {}
        headers["user-agent"] = USER_AGENT
        headers["Content-Type"] = "application/json"
        
        url = endpoint
        if params:
            param_str = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{endpoint}?{param_str}"
        
        try:
            if data:
                data_bytes = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
            else:
                req = urllib.request.Request(url, headers=headers, method=method)
            
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raise PanasonicException(f"HTTP {e.code}: {e.read().decode('utf-8') if hasattr(e, 'read') else str(e)}")
        except Exception as e:
            raise PanasonicException(f"請求失敗: {str(e)}")
    
    def login(self) -> bool:
        try:
            _LOGGER.info(f"嘗試登入: {self.account}")
            response = self._request(
                method="POST",
                endpoint=api_login(),
                data={"MemId": self.account, "PW": self.password, "AppToken": APP_TOKEN}
            )
            if "RefreshToken" not in response or "CPToken" not in response:
                raise PanasonicLoginFailed("登入失敗")
            self._refresh_token = response["RefreshToken"]
            self._cp_token = response["CPToken"]
            _LOGGER.info("✅ 登入成功")
            return True
        except Exception as e:
            _LOGGER.error(f"❌ 登入失敗: {str(e)}")
            raise
    
    def get_devices(self) -> List[Dict]:
        if not self._cp_token: raise PanasonicException("未登入")
        try:
            response = self._request(method="GET", endpoint=api_get_devices(), headers={"cptoken": self._cp_token})
            self._devices = response.get("GwList", [])
            return self._devices
        except Exception as e:
            _LOGGER.error(f"❌ 取得設備清單失敗: {str(e)}")
            raise
    
    def get_device_info(self, device_auth: str, gwid: str) -> Dict:
        if not self._cp_token: raise PanasonicException("未登入")
        try:
            data = {
                "CommandTypes": [
                    {"CommandType": "0x00"},  # 開關
                    {"CommandType": "0x01"},  # 模式
                    {"CommandType": "0x03"},  # 室內溫度 (增加這行！)
                    {"CommandType": "0x04"},  # 設定溫度
                ],
                "DeviceID": 1
            }
            return self._request(
                method="POST",
                endpoint=api_get_device_info(),
                headers={"cptoken": self._cp_token, "auth": device_auth, "gwid": gwid},
                data=data
            )
        except Exception as e:
            _LOGGER.warning(f"⚠️ 取得設備細節失敗: {str(e)}")
            return {}
    
    def set_command(self, device_auth: str, command_type: str, value: int) -> bool:
        if not self._cp_token: raise PanasonicException("未登入")
        try:
            self._request(
                method="GET",
                endpoint=api_set_command(),
                headers={"cptoken": self._cp_token, "auth": device_auth},
                params={"DeviceID": 1, "CommandType": command_type, "Value": value}
            )
            _LOGGER.info(f"✅ 命令發送成功: cmd={command_type}, val={value}")
            return True
        except Exception as e:
            _LOGGER.error(f"❌ 命令發送失敗: {str(e)}")
            raise

# ============================================================================
# FastAPI 應用與路由
# ============================================================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_api_client = None

def get_api_client() -> PanasonicSmartApp:
    global _api_client
    if _api_client is None:
        account = os.getenv("PANASONIC_ACCOUNT")
        password = os.getenv("PANASONIC_PASSWORD")
        if not account or not password:
            raise HTTPException(status_code=500, detail="未設定 PANASONIC_ACCOUNT 或 PANASONIC_PASSWORD")
        _api_client = PanasonicSmartApp(account, password)
        _api_client.login()
    return _api_client

@app.get("/health")
def health_check():
    return {"status": "ok"}

# 萬用 JSON 解析器 (找尋 CommandType 與 Value)
def _extract_status(info_dict):
    result = {}
    def search(d):
        if isinstance(d, dict):
            if "CommandType" in d and "Value" in d:
                result[d["CommandType"]] = d["Value"]
            for v in d.values(): search(v)
        elif isinstance(d, list):
            for item in d: search(item)
    search(info_dict)
    return result

@app.get("/api/devices")
def get_devices(client: PanasonicSmartApp = Depends(get_api_client)):
    """取得設備狀態 (包含溫度與開關)"""
    devices_raw = client.get_devices()
    result_list = []
    
    for d in devices_raw:
        dev_type = int(d.get("DeviceType", 0))
        gwid = d.get("GWID", "")
        auth = d.get("Auth", "")
        is_online = d.get("IsOnline", False)
        
        # 建立基礎資料
        dev_data = {
            "DeviceID": gwid,
            "DeviceName": d.get("NickName", "Unknown"),
            "device_type": dev_type,
            "is_online": is_online,
            "Model": d.get("ModelVersion", ""),
            "IsEnable": 0,
            "CurTemp": "--",
            "Settemp": "--"
        }
        
        # 如果是冷氣 (type=1) 且在線，就去抓最新溫度！
        if dev_type == 1 and is_online:
            info = client.get_device_info(auth, gwid)
            status = _extract_status(info)
            
            # 解析開關狀態 (0x00)
            if "0x00" in status:
                dev_data["IsEnable"] = status["0x00"]
                
            # 解析室內溫度 (0x03)
            if "0x03" in status:
                cur_temp = status["0x03"]
                # 有些機型回傳的是乘以2的數值
                dev_data["CurTemp"] = cur_temp / 2.0 if cur_temp > 40 else cur_temp
                
            # 解析設定溫度 (0x04)
            if "0x04" in status:
                dev_data["Settemp"] = status["0x04"] / 2.0
                
        result_list.append(dev_data)
        
    return {"devices": result_list, "count": len(result_list)}

class ControlRequest(BaseModel):
    CommandID: str
    Value: str

@app.post("/api/devices/{device_id}/control")
def control_device(
    device_id: str,
    request: ControlRequest,
    client: PanasonicSmartApp = Depends(get_api_client)
):
    """專門給前端面板呼叫的控制 API (包含格式翻譯)"""
    # 翻譯前端的 CommandID
    cmd_map = {"1": "0x00", "4": "0x04"}
    cmd_type = cmd_map.get(request.CommandID)
    
    if not cmd_type:
        raise HTTPException(status_code=400, detail="未知的指令類型")
        
    # 處理數值 (溫度設定要乘以2)
    val = int(request.Value)
    if request.CommandID == "4":
        val = int(float(request.Value) * 2)
        
    # 尋找對應設備的 Auth
    device = next((d for d in client._devices if d.get("GWID") == device_id), None)
    if not device:
        client.get_devices() # 重抓一次清單
        device = next((d for d in client._devices if d.get("GWID") == device_id), None)
        if not device:
            raise HTTPException(status_code=404, detail="找不到該設備")
            
    # 送出指令
    client.set_command(device.get("Auth"), cmd_type, val)
    return {"success": True, "message": "指令已送出"}
