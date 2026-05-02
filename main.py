"""
# 版本號：v5.0 (2026-05-02 14:00)
# 更新內容：
# 1. 破解 DeviceGetInfo 格式之謎：補回最外層 JArray 陣列包裝。
# 2. 強制 json.dumps 確保格式不變形。
# 3. 保留完美的 Token 自動重登機制。
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import os
import requests
import json

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://ems2.panasonic.com.tw/api"
APP_TOKEN = "D8CBFF4C-2824-4342-B22D-189166FEF503"
USER_AGENT = "okhttp/4.9.1"

class PanasonicException(Exception): pass
class PanasonicLoginFailed(PanasonicException): pass

class PanasonicSmartApp:
    def __init__(self, account: str, password: str):
        self.account = account
        self.password = password
        self._cp_token: Optional[str] = None
        self._devices: List[Dict] = []
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT
        })

    def login(self) -> bool:
        r = self._session.post(
            f"{BASE_URL}/userlogin1",
            json={"MemId": self.account, "PW": self.password, "AppToken": APP_TOKEN}
        )
        r.raise_for_status()
        data = r.json()
        if "CPToken" not in data:
            raise PanasonicLoginFailed(f"登入失敗: {data}")
        self._cp_token = data["CPToken"]
        _LOGGER.info("✅ 登入成功，取得新 Token")
        return True

    def get_devices(self) -> List[Dict]:
        headers = {"cptoken": self._cp_token}
        r = self._session.get(f"{BASE_URL}/UserGetRegisteredGwList2", headers=headers)
        
        # 處理 Token 逾時自動重登
        if r.status_code == 417 and "CPToken" in r.text:
            _LOGGER.warning("⚠️ Token 已逾時，正在自動重新登入...")
            self.login()
            headers["cptoken"] = self._cp_token
            r = self._session.get(f"{BASE_URL}/UserGetRegisteredGwList2", headers=headers)

        if r.status_code != 200:
            _LOGGER.error(f"取得設備清單失敗: {r.text}")
            
        r.raise_for_status()
        self._devices = r.json().get("GwList", [])
        return self._devices

    def get_device_info(self, auth: str, gwid: str) -> Dict:
        # 【終極修正】：最外層加上 [] 陣列，完美符合伺服器 JArray 期待
        payload = [{
            "DeviceID": 1,
            "CommandTypes": [
                {"CommandType": "0x00"}, # 開關狀態
                {"CommandType": "0x01"}, # 運轉模式
                {"CommandType": "0x03"}, # 室內溫度
                {"CommandType": "0x04"}  # 設定溫度
            ]
        }]
        
        headers = {
            "cptoken": self._cp_token, 
            "auth": auth, 
            "gwid": gwid,
            "Content-Type": "application/json"
        }
        
        # 強制轉為字串發送，避免套件自作聰明
        data_str = json.dumps(payload)
        r = self._session.post(f"{BASE_URL}/DeviceGetInfo", headers=headers, data=data_str)
        
        # 處理 Token 逾時自動重登
        if r.status_code == 417 and "CPToken" in r.text:
            self.login()
            headers["cptoken"] = self._cp_token
            r = self._session.post(f"{BASE_URL}/DeviceGetInfo", headers=headers, data=data_str)

        if r.status_code != 200:
            _LOGGER.warning(f"⚠️ 取得設備狀態失敗 [{gwid}]: HTTP {r.status_code} - {r.text}")
            return {}
            
        r.raise_for_status()
        return r.json()

    def set_command(self, auth: str, command_type: str, value: int) -> bool:
        headers = {"cptoken": self._cp_token, "auth": auth}
        params = {"DeviceID": 1, "CommandType": command_type, "Value": value}
        
        r = self._session.get(f"{BASE_URL}/DeviceSetCommand", headers=headers, params=params)
        
        # 處理 Token 逾時自動重登
        if r.status_code == 417 and "CPToken" in r.text:
            self.login()
            headers["cptoken"] = self._cp_token
            r = self._session.get(f"{BASE_URL}/DeviceSetCommand", headers=headers, params=params)

        if r.status_code != 200:
            _LOGGER.error(f"發送指令失敗: {r.text}")
            
        r.raise_for_status()
        _LOGGER.info(f"✅ 發送指令 {command_type}={value} 成功")
        return True


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
            raise HTTPException(status_code=500, detail="未設定帳密環境變數")
        _api_client = PanasonicSmartApp(account, password)
        _api_client.login()
    return _api_client

def _extract_status(info_dict):
    result = {}
    def search(d):
        if isinstance(d, dict):
            if "CommandType" in d and "Value" in d:
                result[d["CommandType"]] = d["Value"]
            for v in d.values():
                search(v)
        elif isinstance(d, list):
            for item in d:
                search(item)
    search(info_dict)
    return result

@app.get("/health")
def health_check():
    return {"status": "ok"}

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
            "is_online": False,
            "Model": d.get("Model", ""),
            "IsEnable": 0,
            "CurTemp": "--",
            "Settemp": "--"
        }
        if dev_type == 1:
            info = client.get_device_info(auth, gwid)
            status = _extract_status(info)
            if status:
                dev_data["is_online"] = True
                if "0x00" in status:
                    dev_data["IsEnable"] = status["0x00"]
                if "0x03" in status:
                    cur = status["0x03"]
                    dev_data["CurTemp"] = cur / 2.0 if cur > 40 else cur
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
    if not cmd_type:
        raise HTTPException(status_code=400, detail="未知指令")
    val = int(request.Value)
    if request.CommandID == "4":
        val = int(float(request.Value) * 2)
    device = next((d for d in client._devices if d.get("GWID") == device_id), None)
    if not device:
        client.get_devices()
        device = next((d for d in client._devices if d.get("GWID") == device_id), None)
        if not device:
            raise HTTPException(status_code=404, detail="找不到設備")
    client.set_command(device.get("Auth"), cmd_type, val)
    return {"success": True}

@app.get("/api/debug")
def debug_one_device(client: PanasonicSmartApp = Depends(get_api_client)):
    devices = client.get_devices()
    if not devices:
        return {"error": "沒有設備"}
    first = devices[0]
    auth = first.get("Auth", "")
    gwid = first.get("GWID", "")
    
    # 直接暴力印出完整 HTTP 回應
    headers = {
        "cptoken": client._cp_token,
        "auth": auth,
        "gwid": gwid,
        "Content-Type": "application/json"
    }
    payload = json.dumps([{
        "DeviceID": 1,
        "CommandTypes": [
            {"CommandType": "0x00"},
            {"CommandType": "0x03"},
            {"CommandType": "0x04"}
        ]
    }])
    
    r = client._session.post(f"{BASE_URL}/DeviceGetInfo", headers=headers, data=payload)
    
    return {
        "gwid": gwid,
        "http_status": r.status_code,
        "response_text": r.text,
        "response_json": r.json() if r.headers.get("content-type","").startswith("application/json") else None
    }
