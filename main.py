from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import logging
import os
import requests

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
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json"
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
        _LOGGER.info("登入成功")
        return True

    def get_devices(self) -> List[Dict]:
        r = self._session.get(
            f"{BASE_URL}/UserGetRegisteredGwList2",
            headers={"cptoken": self._cp_token}
        )
        r.raise_for_status()
        self._devices = r.json().get("GwList", [])
        return self._devices

    def get_device_info(self, auth: str, gwid: str) -> Dict:
        try:
            r = self._session.post(
                f"{BASE_URL}/DeviceGetInfo",
                headers={"cptoken": self._cp_token, "auth": auth, "gwid": gwid},
                json={
                    "CommandTypes": [
                        {"CommandType": "0x00"},
                        {"CommandType": "0x01"},
                        {"CommandType": "0x03"},
                        {"CommandType": "0x04"},
                    ],
                    "DeviceID": 1
                }
            )
            _LOGGER.info(f"DeviceGetInfo [{gwid}] HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            _LOGGER.error(f"get_device_info [{gwid}] 失敗: {e}")
            return {}

    def set_command(self, auth: str, command_type: str, value: int) -> bool:
        r = self._session.get(
            f"{BASE_URL}/DeviceSetCommand",
            headers={"cptoken": self._cp_token, "auth": auth},
            params={"DeviceID": 1, "CommandType": command_type, "Value": value}
        )
        _LOGGER.info(f"SetCommand {command_type}={value} HTTP {r.status_code}: {r.text[:200]}")
        r.raise_for_status()
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

@app.get("/api/debug")
def debug_one_device(client: PanasonicSmartApp = Depends(get_api_client)):
    devices = client.get_devices()
    if not devices:
        return {"error": "沒有設備"}
    first = devices[0]
    info = client.get_device_info(first.get("Auth", ""), first.get("GWID", ""))
    return {"device_raw": first, "device_info_response": info}

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
