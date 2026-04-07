"""
OneKey 钱包实现 (适配新基类)
"""

import json
from decimal import Decimal
from typing import Dict, Optional

from wallet_base import BaseWallet


class OneKeyWallet(BaseWallet):
    """OneKey Pro 硬件钱包"""
    
    def __init__(self, bridge_url: str = "http://localhost:21320"):
        super().__init__("onekey")
        self.bridge_url = bridge_url
        self.device_id: Optional[str] = None
    
    async def connect(self) -> bool:
        """连接 OneKey Bridge"""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                # 获取设备列表
                payload = {"type": "enumerate"}
                async with session.post(f"{self.bridge_url}/", json=payload) as resp:
                    devices = await resp.json()
                    
                    if not devices or not isinstance(devices, list):
                        print("❌ OneKey: 未找到设备")
                        return False
                    
                    # 使用第一个设备
                    self.device_id = devices[0].get("path", devices[0].get("session"))
                    self.connected = True
                    print(f"✅ OneKey: 已连接 {self.device_id}")
                    return True
                    
        except Exception as e:
            print(f"❌ OneKey 连接失败: {e}")
            return False
    
    async def get_address(self) -> Optional[str]:
        """获取地址"""
        if not self.connected:
            if not await self.connect():
                return None
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "device": self.device_id,
                    "path": "m/44'/60'/0'/0/0",
                    "showOnTrezor": True
                }
                
                async with session.post(
                    f"{self.bridge_url}/ethereum/getAddress",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    self.address = result.get("address")
                    return self.address
                    
        except Exception as e:
            print(f"❌ 获取地址失败: {e}")
            return None
    
    async def sign_transaction(self, tx_data: Dict) -> Dict:
        """请求 OneKey 签名"""
        if not self.connected:
            if not await self.connect():
                return {"success": False, "error": "未连接"}
        
        try:
            import aiohttp
            
            print("🔐 请在 OneKey 设备上确认交易...")
            
            # 构建 OneKey 签名请求
            payload = {
                "device": self.device_id,
                "path": "m/44'/60'/0'/0/0",
                "transaction": {
                    "to": tx_data["to"],
                    "value": str(tx_data.get("value", 0)),
                    "data": tx_data.get("data", "0x"),
                    "chainId": tx_data.get("chain_id", 8453),
                    "gasLimit": str(tx_data.get("gas", 200000)),
                    "maxFeePerGas": str(tx_data.get("maxFeePerGas", "1000000000")),
                    "maxPriorityFeePerGas": str(tx_data.get("maxPriorityFeePerGas", "100000000"))
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.bridge_url}/ethereum/signTransaction",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    
                    if "signature" in result:
                        return {
                            "success": True,
                            "signature": result["signature"],
                            "onekey_confirmed": True
                        }
                    else:
                        return {
                            "success": False,
                            "error": result.get("error", "签名失败")
                        }
                        
        except Exception as e:
            print(f"❌ 签名失败: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_balance(self, token: str = "ETH") -> Decimal:
        """获取余额"""
        # OneKey 不直接提供余额查询，需要通过 Web3
        return Decimal("0")
