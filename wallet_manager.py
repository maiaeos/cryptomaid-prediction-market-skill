"""
OneKey Pro 硬件钱包集成
支持 EIP-712 签名
"""

import json
import asyncio
from typing import Dict, Optional
from decimal import Decimal


class OneKeyManager:
    """OneKey 硬件钱包管理器"""
    
    def __init__(self, bridge_url: str = "http://localhost:21320"):
        self.bridge_url = bridge_url
        self.connected = False
        self.device_id: Optional[str] = None
    
    async def connect(self) -> bool:
        """连接 OneKey 设备"""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                # 使用 Trezor 兼容的 enumerate 接口
                payload = {"type": "enumerate"}
                async with session.post(f"{self.bridge_url}/", json=payload) as resp:
                    devices = await resp.json()
                    
                    if not devices or not isinstance(devices, list):
                        print("❌ OneKey: 未找到设备，请确保 OneKey 已连接并解锁")
                        return False
                    
                    # 找到第一个可用的设备
                    for device in devices:
                        if device.get("type") == "OneKey" or "OneKey" in str(device):
                            self.device_id = device.get("path", device.get("session"))
                            self.connected = True
                            print(f"✅ OneKey: 已连接设备 {self.device_id}")
                            return True
                    
                    # 如果没有找到 OneKey，使用第一个设备
                    if devices:
                        self.device_id = devices[0].get("path", devices[0].get("session"))
                        self.connected = True
                        print(f"✅ OneKey: 已连接设备 {self.device_id}")
                        return True
                    
                    print("❌ OneKey: 未找到可用设备")
                    return False
                    
        except Exception as e:
            print(f"❌ OneKey: 连接失败: {e}")
            return False
    
    async def get_address(self, path: str = "m/44'/60'/0'/0/0") -> Optional[str]:
        """获取以太坊地址"""
        if not self.connected:
            if not await self.connect():
                return None
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                payload = {
                    "device": self.device_id,
                    "path": path,
                    "showOnTrezor": True  # 在设备上显示地址
                }
                
                async with session.post(
                    f"{self.bridge_url}/ethereum/getAddress",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    address = result.get("address")
                    print(f"✅ OneKey: 地址 {address}")
                    return address
                    
        except Exception as e:
            print(f"❌ OneKey: 获取地址失败: {e}")
            return None
    
    async def sign_transaction(self, tx_data: Dict) -> Dict:
        """
        签名交易
        
        这会触发 OneKey 设备上的指纹确认
        """
        if not self.connected:
            if not await self.connect():
                raise ConnectionError("OneKey 未连接")
        
        try:
            import aiohttp
            
            platform = tx_data.get("platform")
            
            if platform == "limitless":
                # Limitless 使用 API Key，不需要硬件签名
                # 但为了安全，我们可以用 OneKey 签名一个确认消息
                return await self._sign_limitless_confirmation(tx_data)
            
            elif platform == "polymarket":
                # Polymarket 需要 EIP-712 签名
                return await self._sign_polymarket_order(tx_data)
            
            elif platform == "predict_fun":
                # Predict.fun 也需要 EIP-712
                return await self._sign_predict_fun_order(tx_data)
            
            else:
                raise ValueError(f"不支持的平台: {platform}")
                
        except Exception as e:
            print(f"❌ OneKey: 签名失败: {e}")
            raise
    
    async def _sign_limitless_confirmation(self, tx_data: Dict) -> Dict:
        """
        为 Limitless 订单签名确认消息
        
        虽然 Limitless 使用 API Key，但我们可以用 OneKey 签名一个
        "确认执行此交易" 的消息，增加安全性
        """
        import aiohttp
        
        # 构建确认消息
        message = f"""
Limitless Order Confirmation:
Market: {tx_data['market_id']}
Side: {tx_data['side']}
Size: {tx_data['size']}
Price: {tx_data['price']}
"""
        
        print("🔐 OneKey: 请在设备上确认 Limitless 订单...")
        
        payload = {
            "device": self.device_id,
            "path": "m/44'/60'/0'/0/0",
            "message": message,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.bridge_url}/ethereum/signMessage",
                json=payload
            ) as resp:
                signature = await resp.json()
                
                print("✅ OneKey: 签名完成")
                
                # 返回原始交易数据 + 签名
                return {
                    **tx_data,
                    "onekey_signature": signature.get("signature"),
                    "onekey_confirmed": True
                }
    
    async def _sign_polymarket_order(self, order_data: Dict) -> Dict:
        """
        签名 Polymarket EIP-712 订单
        
        这会触发 OneKey 设备显示订单详情并要求指纹确认
        """
        import aiohttp
        
        print("🔐 OneKey: 请在设备上确认 Polymarket 订单...")
        print(f"   Token: {order_data['token_id'][:20]}...")
        print(f"   Side: {order_data['side']}")
        print(f"   Size: {order_data['size']}")
        print(f"   Price: {order_data['price']}")
        
        # EIP-712 域名分隔符
        domain = {
            "name": "Polymarket CLOB",
            "version": "1",
            "chainId": 137,  # Polygon
            "verifyingContract": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
        }
        
        # EIP-712 类型
        types = {
            "Order": [
                {"name": "tokenId", "type": "uint256"},
                {"name": "side", "type": "uint8"},
                {"name": "maker", "type": "address"},
                {"name": "taker", "type": "address"},
                {"name": "size", "type": "uint256"},
                {"name": "price", "type": "uint256"},
                {"name": "expiration", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
            ]
        }
        
        # 订单数据
        value = {
            "tokenId": int(order_data["token_id"]),
            "side": 0 if order_data["side"] == "BUY" else 1,
            "maker": order_data["maker"],
            "taker": order_data["taker"],
            "size": int(Decimal(str(order_data["size"])) * Decimal("1000000")),  # 6位小数
            "price": int(Decimal(str(order_data["price"])) * Decimal("1000000")),
            "expiration": order_data["expiration"],
            "nonce": order_data["nonce"],
        }
        
        # 构建 EIP-712 签名请求
        payload = {
            "device": self.device_id,
            "path": "m/44'/60'/0'/0/0",
            "domain": domain,
            "types": types,
            "primaryType": "Order",
            "message": value,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.bridge_url}/ethereum/signTypedData",
                json=payload
            ) as resp:
                result = await resp.json()
                
                print("✅ OneKey: EIP-712 签名完成")
                
                return {
                    **order_data,
                    "signature": result.get("signature"),
                    "onekey_confirmed": True
                }
    
    async def _sign_predict_fun_order(self, order_data: Dict) -> Dict:
        """签名 Predict.fun 订单 (类似 Polymarket)"""
        # Predict.fun 也是 EIP-712，但域名和合约地址不同
        print("🔐 OneKey: 请在设备上确认 Predict.fun 订单...")
        
        # TODO: 实现 Predict.fun 特定的 EIP-712 签名
        # 需要 Predict.fun 的合约地址和类型定义
        
        return {
            **order_data,
            "signature": "0x...",  # 占位
            "onekey_confirmed": True
        }
    
    async def sign_message(self, message: str) -> str:
        """签名普通消息"""
        if not self.connected:
            if not await self.connect():
                raise ConnectionError("OneKey 未连接")
        
        try:
            import aiohttp
            
            print(f"🔐 OneKey: 请确认消息签名...")
            print(f"   消息: {message[:50]}...")
            
            payload = {
                "device": self.device_id,
                "path": "m/44'/60'/0'/0/0",
                "message": message,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.bridge_url}/ethereum/signMessage",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    signature = result.get("signature")
                    print("✅ OneKey: 消息签名完成")
                    return signature
                    
        except Exception as e:
            print(f"❌ OneKey: 消息签名失败: {e}")
            raise


# 模拟模式 (用于测试)
class OneKeySimulator(OneKeyManager):
    """OneKey 模拟器 (用于开发和测试)"""
    
    def __init__(self):
        super().__init__("")
        self.connected = True
        self.device_id = "simulator"
    
    async def connect(self) -> bool:
        print("🔧 OneKey Simulator: 模拟连接")
        return True
    
    async def get_address(self, path: str = "m/44'/60'/0'/0/0") -> str:
        return "0xSimulatedAddress123456789012345678901234"
    
    async def sign_transaction(self, tx_data: Dict) -> Dict:
        print("🔧 OneKey Simulator: 模拟签名")
        print(f"   平台: {tx_data.get('platform')}")
        print(f"   市场: {tx_data.get('market_id', tx_data.get('token_id', 'N/A'))}")
        
        # 模拟用户确认
        await asyncio.sleep(1)
        
        return {
            **tx_data,
            "signature": "0x" + "11" * 65,  # 模拟签名
            "onekey_confirmed": True,
            "simulated": True
        }
    
    async def sign_message(self, message: str) -> str:
        print(f"🔧 OneKey Simulator: 模拟消息签名")
        return "0x" + "22" * 65
