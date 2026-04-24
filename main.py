"""
Panasonic IoT TW FastAPI 後端
基於 osk2/panasonic_smart_app 的開源程式碼改造
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import aiohttp
import asyncio
import logging
import os
from datetime import datetime

# 配置日誌
logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

# ============================================================================
# 常數定義
# ============================================================================

BASE_URL = "https://ems2.panasonic.com.tw/api"
APP_TOKEN = "D8CBFF4C-2824-4342-B22D-189166FEF503"
USER_AGENT = "okhttp/4.9.1"
SECONDS_BETWEEN_REQUEST = 2
REQUEST_TIMEOUT = 20

# ============================================================================
# 自訂例外
# ============================================================================

class PanasonicException(Exception):
    """Panasonic API 基礎異常"""
    pass

class PanasonicLoginFailed(PanasonicException):
    """登入失敗"""
    pass

class PanasonicTokenExpired(PanasonicException):
    """令牌過期"""
    pass

# ============================================================================
# API URLs
# ============================================================================

def api_login():
    return f"{BASE_URL}/userlogin1"

def api_get_devices():
    return f"{BASE_URL}/UserGetRegisteredGwList2"

def api_get_device_info():
    return f"{BASE_URL}/DeviceGetInfo"

def api_set_command():
    return f"{BASE_URL}/DeviceSetCommand"

def api_refresh_token():
    return f"{BASE_URL}/RefreshToken1"

def api_get_overview():
    return f"{BASE_URL}/UserGetDeviceStatus"

# ============================================================================
# Panasonic Smart App API 客戶端
# ============================================================================

class PanasonicSmartApp:
    """Panasonic IoT TW API 客戶端 - 基於開源實現"""
    
    def __init__(self, account: str, password: str):
        self.account = account
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._cp_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._devices: List[Dict] = []
    
    async def _ensure_session(self):
        """確保 session 存在"""
        if not self._session:
            self._session = aiohttp.ClientSession()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        headers: Dict = None,
        data: Dict = None,
        params: Dict = None
    ) -> Dict:
        """
        發送 HTTP 請求
        
        Args:
            method: HTTP 方法 (GET, POST)
            endpoint: API 端點
            headers: HTTP headers
            data: 請求數據
            params: URL 參數
            
        Returns:
            Dict: 響應 JSON
            
        Raises:
            PanasonicException: 請求失敗
        """
        await self._ensure_session()
        
        if headers is None:
            headers = {}
        
        headers["user-agent"] = USER_AGENT
        
        try:
            async with self._session.request(
                method,
                url=endpoint,
                json=data,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                text = await response.text()
                
                if response.status == 200:
                    try:
                        return await response.json()
                    except:
                        raise PanasonicException(f"無法解析響應: {text}")
                elif response.status == 403:
                    raise PanasonicException(f"訪問被拒絕: {text}")
                else:
                    raise PanasonicException(f"HTTP {response.status}: {text}")
        
        except asyncio.TimeoutError:
            raise PanasonicException("請求超時")
        except Exception as e:
            raise PanasonicException(f"請求失敗: {str(e)}")
    
    async def login(self) -> bool:
        """
        登入 Panasonic IoT TW
        
        Returns:
            bool: 是否登入成功
        """
        try:
            _LOGGER.info(f"嘗試登入: {self.account}")
            
            data = {
                "MemId": self.account,
                "PW": self.password,
                "AppToken": APP_TOKEN
            }
            
            response = await self._request(
                method="POST",
                endpoint=api_login(),
                data=data
            )
            
            if "RefreshToken" not in response or "CPToken" not in response:
                raise PanasonicLoginFailed(f"登入失敗: {response}")
            
            self._refresh_token = response["RefreshToken"]
            self._cp_token = response["CPToken"]
            
            _LOGGER.info("✅ 登入成功")
            return True
        
        except Exception as e:
            _LOGGER.error(f"❌ 登入失敗: {str(e)}")
            raise PanasonicLoginFailed(str(e))
    
    async def refresh_tokens(self):
        """刷新令牌"""
        if not self._refresh_token:
            raise PanasonicException("無刷新令牌")
        
        try:
            data = {"RefreshToken": self._refresh_token}
            response = await self._request(
                method="POST",
                endpoint=api_refresh_token(),
                data=data
            )
            
            self._cp_token = response.get("CPToken")
            self._refresh_token = response.get("RefreshToken")
            
            _LOGGER.info("✅ 令牌已刷新")
        
        except Exception as e:
            _LOGGER.error(f"❌ 令牌刷新失敗: {str(e)}")
            raise
    
    async def get_devices(self) -> List[Dict]:
        """
        取得所有已註冊的設備
        
        Returns:
            List[Dict]: 設備列表
        """
        if not self._cp_token:
            raise PanasonicException("未登入")
        
        try:
            headers = {"cptoken": self._cp_token}
            response = await self._request(
                method="GET",
                endpoint=api_get_devices(),
                headers=headers
            )
            
            self._devices = response.get("GwList", [])
            _LOGGER.info(f"✅ 取得 {len(self._devices)} 個設備")
            return self._devices
        
        except Exception as e:
            _LOGGER.error(f"❌ 取得設備失敗: {str(e)}")
            raise
    
    async def get_device_info(self, device_auth: str, gwid: str) -> Dict:
        """
        取得單個設備的詳細信息
        
        Args:
            device_auth: 設備的 Auth ID
            gwid: Gateway ID
            
        Returns:
            Dict: 設備信息
        """
        if not self._cp_token:
            raise PanasonicException("未登入")
        
        try:
            headers = {
                "cptoken": self._cp_token,
                "auth": device_auth,
                "gwid": gwid
            }
            
            data = {
                "CommandTypes": [
                    {"CommandType": "0x00"},  # 開關
                    {"CommandType": "0x01"},  # 模式
                    {"CommandType": "0x04"},  # 溫度
                    {"CommandType": "0x06"},  # 風速
                    {"CommandType": "0x07"},  # 左右搖擺
                    {"CommandType": "0x08"},  # 上下搖擺
                ],
                "DeviceID": 1
            }
            
            response = await self._request(
                method="POST",
                endpoint=api_get_device_info(),
                headers=headers,
                data=[data]
            )
            
            return response
        
        except Exception as e:
            _LOGGER.warning(f"⚠️ 取得設備信息失敗: {str(e)}")
            return {}
    
    async def set_command(
        self,
        device_auth: str,
        command_type: str,
        value: int,
        device_id: int = 1
    ) -> bool:
        """
        設定設備命令
        
        Args:
            device_auth: 設備的 Auth ID
            command_type: 命令類型 (如 "0x00" 開關)
            value: 命令值
            device_id: 設備 ID (通常為 1)
            
        Returns:
            bool: 是否設定成功
        """
        if not self._cp_token:
            raise PanasonicException("未登入")
        
        try:
            headers = {
                "cptoken": self._cp_token,
                "auth": device_auth
            }
            
            params = {
                "DeviceID": device_id,
                "CommandType": command_type,
                "Value": value
            }
            
            await self._request(
                method="GET",
                endpoint=api_set_command(),
                headers=headers,
                params=params
            )
            
            _LOGGER.info(f"✅ 命令設定成功: type={command_type}, value={value}")
            return True
        
        except Exception as e:
            _LOGGER.error(f"❌ 命令設定失敗: {str(e)}")
            raise
    
    async def close(self):
        """關閉 session"""
        if self._session:
            await self._session.close()

# ============================================================================
# FastAPI 應用
# ============================================================================

app = FastAPI(
    title="Panasonic IoT TW 控制",
    description="遠端控制 Panasonic 冷氣",
    version="1.0.0"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# 全域 API 客戶端實例
# ============================================================================

_api_client: Optional[PanasonicSmartApp] = None

async def get_api_client() -> PanasonicSmartApp:
    """取得 API 客戶端"""
    global _api_client
    
    if _api_client is None:
        # 從環境變數取得帳密
        account = os.getenv("PANASONIC_ACCOUNT")
        password = os.getenv("PANASONIC_PASSWORD")
        
        if not account or not password:
            raise HTTPException(
                status_code=500,
                detail="未設定 PANASONIC_ACCOUNT 或 PANASONIC_PASSWORD"
            )
        
        _api_client = PanasonicSmartApp(account, password)
        await _api_client.login()
    
    return _api_client

# ============================================================================
# Pydantic Models
# ============================================================================

class LoginRequest(BaseModel):
    """登入請求"""
    account: str
    password: str

class LoginResponse(BaseModel):
    """登入響應"""
    success: bool
    message: str

class Device(BaseModel):
    """設備信息"""
    id: str
    name: str
    auth: str
    gwid: str
    device_type: int
    is_online: bool
    model: Optional[str] = None

class DeviceListResponse(BaseModel):
    """設備列表響應"""
    devices: List[Device]
    count: int

class CommandRequest(BaseModel):
    """命令請求"""
    device_id: str
    command_type: str
    value: int

class CommandResponse(BaseModel):
    """命令響應"""
    success: bool
    message: str

# ============================================================================
# API 路由
# ============================================================================

@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    登入 Panasonic IoT TW
    
    Args:
        request.account: Email 或手機號碼
        request.password: 密碼
    """
    global _api_client
    
    try:
        _api_client = PanasonicSmartApp(request.account, request.password)
        await _api_client.login()
        
        return LoginResponse(
            success=True,
            message="登入成功"
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"登入失敗: {str(e)}"
        )

@app.get("/api/devices", response_model=DeviceListResponse)
async def get_devices(client: PanasonicSmartApp = Depends(get_api_client)):
    """取得所有設備"""
    try:
        devices_raw = await client.get_devices()
        
        devices = [
            Device(
                id=d.get("GWID", ""),
                name=d.get("NickName", "Unknown"),
                auth=d.get("Auth", ""),
                gwid=d.get("GWID", ""),
                device_type=int(d.get("DeviceType", 0)),
                is_online=d.get("IsOnline", False),
                model=d.get("ModelVersion", "")
            )
            for d in devices_raw
        ]
        
        return DeviceListResponse(
            devices=devices,
            count=len(devices)
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"取得設備失敗: {str(e)}"
        )

@app.post("/api/devices/{device_id}/command", response_model=CommandResponse)
async def send_command(
    device_id: str,
    request: CommandRequest,
    client: PanasonicSmartApp = Depends(get_api_client)
):
    """
    發送命令到設備
    
    Args:
        device_id: 設備 ID (GWID)
        request.command_type: 命令類型 (如 "0x00" 開關, "0x04" 溫度)
        request.value: 命令值
    """
    try:
        # 找到對應的設備
        device = next(
            (d for d in client._devices if d.get("GWID") == device_id),
            None
        )
        
        if not device:
            raise HTTPException(
                status_code=404,
                detail=f"設備未找到: {device_id}"
            )
        
        device_auth = device.get("Auth")
        
        # 發送命令
        await client.set_command(
            device_auth=device_auth,
            command_type=request.command_type,
            value=request.value
        )
        
        return CommandResponse(
            success=True,
            message="命令發送成功"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"命令發送失敗: {str(e)}"
        )

# 簡便方法：開/關、設定溫度

@app.post("/api/devices/{device_id}/turn-on", response_model=CommandResponse)
async def turn_on(
    device_id: str,
    client: PanasonicSmartApp = Depends(get_api_client)
):
    """開啟冷氣"""
    return await send_command(
        device_id,
        CommandRequest(device_id=device_id, command_type="0x00", value=1),
        client
    )

@app.post("/api/devices/{device_id}/turn-off", response_model=CommandResponse)
async def turn_off(
    device_id: str,
    client: PanasonicSmartApp = Depends(get_api_client)
):
    """關閉冷氣"""
    return await send_command(
        device_id,
        CommandRequest(device_id=device_id, command_type="0x00", value=0),
        client
    )

@app.post("/api/devices/{device_id}/set-temperature", response_model=CommandResponse)
async def set_temperature(
    device_id: str,
    temperature: float,
    client: PanasonicSmartApp = Depends(get_api_client)
):
    """
    設定溫度
    
    Args:
        device_id: 設備 ID
        temperature: 溫度 (例如 26.0)
    """
    # 溫度以 0.5 度為單位，存儲為整數
    temp_value = int(temperature * 2)
    
    return await send_command(
        device_id,
        CommandRequest(device_id=device_id, command_type="0x04", value=temp_value),
        client
    )

@app.on_event("shutdown")
async def shutdown():
    """應用關閉時清理"""
    global _api_client
    if _api_client:
        await _api_client.close()

# ============================================================================
# 主程序
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
