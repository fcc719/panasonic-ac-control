"""
Panasonic IoT TW FastAPI 後端
包含即時狀態查詢與前端相容 API (強制連線版)
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

# 常數定義
BASE_URL = "https://ems2.panasonic.com.tw/api"
APP_TOKEN = "D8CBFF4C-2824-4342-B22D-189166FEF503"
USER_AGENT = "okhttp/4.9.1"

class PanasonicException(Exception): pass
class PanasonicLoginFailed(PanasonicException): pass

# API URLs
def api_login(): return f"{BASE_URL}/userlogin1"
def api_get_devices(): return f"{BASE_URL}/UserGetRegisteredGwList2"
def api_get_device_info(): return f"{BASE_URL}/DeviceGetInfo"
def api_set_command(): return f"{BASE_URL}/DeviceSetCommand"

class PanasonicSmartApp:
    def __init__(self, account: str, password: str):
        self.account = account
        self.password = password
        self._cp_token: Optional[str] = None
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
            raise PanasonicException(f"HTTP {e.code}")
        except Exception as e:
            raise PanasonicException(f"請求失敗: {str(e)}")
    
    def login(self) -> bool:
        try:
            response = self._request(
                method="POST",
                endpoint=api_login(),
                data={"MemId": self.account, "PW": self.password, "AppToken": APP_TOKEN}
            )
            if "CPToken" not in response:
                raise PanasonicLoginFailed("登入失敗")
            self._cp_token = response["CPToken"]
            return True
        except Exception as e:
            raise
    
    def get_devices(self) -> List[Dict]:
        if not self._cp_token: raise PanasonicException("未登入")
        response = self._request(method="GET", endpoint=api_get_devices(), headers={"cptoken": self._cp_token})
        self._devices = response.get("GwList", [])
        return self._devices
    
def get_device_info(self, device_auth: str, gwid: str) -> Dict:
    if not self._cp_token: raise PanasonicException("未登入")
    try:
        data = {
            "CommandTypes": [
                {"CommandType": "0x00"},
                {"CommandType": "0x01"},
                {"CommandType": "0x03"},
                {"CommandType": "0x04"},
            ],
            "DeviceID": 1
        }
        result = self._request(
            method="POST",
            endpoint=api_get_device_info(),
            headers={"cptoken": self._cp_token, "auth": device_auth, "gwid": gwid},
            data=data
        )
        _LOGGER.info(f"get_device_info [{gwid}] 回傳: {result}")
        return result
    except Exception as e:
        _LOGGER.error(f"get_device_info [{gwid}] 失敗: {str(e)}")  # 改成印出來
        return {}
    
    def set_command(self, device_auth: str, command_type: str, value: int) -> bool:
        if not self._cp_token: raise PanasonicException("未登入")
        self._request(
            method="GET",
            endpoint=api_set_command(),
            headers={"cptoken": self._cp_token, "auth": device_auth},
            params={"DeviceID": 1, "CommandType": command_type, "Value": value}
        )
        return True

# FastAPI 應用
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
            raise HTTPException(status_code=500, detail="未設定帳密")
        _api_client = PanasonicSmartApp(account, password)
        _api_client.login()
    return _api_client

@app.get("/health")
def health_check():
    return {"status": "ok"}

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
    devices_raw = client.get_devices()
    result_list = []
    
    for d in devices_raw:
        dev_type = int(d.get("DeviceType", 0))
        gwid = d.get("GWID", "")
        auth = d.get("Auth", "")
        
        dev_data = {
            "DeviceID": gwid,
            "DeviceName": d.get("NickName", "Unknown"),
            "device_type": dev_type,
            "is_online": False, # 預設先當作離線
            "Model": d.get("ModelVersion", ""),
            "IsEnable": 0,
            "CurTemp": "--",
            "Settemp": "--"
        }
        
        # 霸王硬上弓：不管清單說什麼，只要是冷氣，就強制去要溫度！
        if dev_type == 1:
            info = client.get_device_info(auth, gwid)
            status = _extract_status(info)
            
            # 如果它有回傳溫度或狀態給我們，代表它活著！(強制改為上線)
            if status:
                dev_data["is_online"] = True
                
                if "0x00" in status:
                    dev_data["IsEnable"] = status["0x00"]
                if "0x03" in status:
                    cur_temp = status["0x03"]
                    dev_data["CurTemp"] = cur_temp / 2.0 if cur_temp > 40 else cur_temp
                if "0x04" in status:
                    dev_data["Settemp"] = status["0x04"] / 2.0
                    
        result_list.append(dev_data)
        
    return {"devices": result_list, "count": len(result_list)}

class ControlRequest(BaseModel):
    CommandID: str
    Value: str

@app.post("/api/devices/{device_id}/control")
def control_device(device_id: str, request: ControlRequest, client: PanasonicSmartApp = Depends(get_api_client)):
    cmd_map = {"1": "0x00", "4": "0x04"}
    cmd_type = cmd_map.get(request.CommandID)
    if not cmd_type: raise HTTPException(status_code=400, detail="未知指令")
        
    val = int(request.Value)
    if request.CommandID == "4": val = int(float(request.Value) * 2)
        
    device = next((d for d in client._devices if d.get("GWID") == device_id), None)
    if not device:
        client.get_devices()
        device = next((d for d in client._devices if d.get("GWID") == device_id), None)
        if not device: raise HTTPException(status_code=404, detail="找不到設備")
            
    client.set_command(device.get("Auth"), cmd_type, val)
    return {"success": True}
