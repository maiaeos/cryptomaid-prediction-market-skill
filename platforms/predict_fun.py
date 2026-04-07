"""
Predict.fun 平台集成
基于官方 SDK 和 API
"""

import aiohttp
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from .base import PredictionMarket, Market, Order, Position


class PredictFunPlatform(PredictionMarket):
    """Predict.fun 平台实现"""
    
    BASE_URL = "https://api.predict.fun"
    
    def __init__(self, api_key: str, private_key: Optional[str] = None, rpc_url: Optional[str] = None):
        super().__init__("predict_fun")
        self.api_key = api_key
        self.private_key = private_key
        self.rpc_url = rpc_url
        self._session: Optional[aiohttp.ClientSession] = None
        
        # JWT token (需要动态获取)
        self.jwt_token: Optional[str] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self._session is None or self._session.closed:
            headers = {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            if self.jwt_token:
                headers["Authorization"] = f"Bearer {self.jwt_token}"
            
            self._session = aiohttp.ClientSession(headers=headers)
        
        return self._session
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        auth: bool = True
    ) -> Dict:
        """发送 API 请求"""
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        
        headers = {}
        if auth and self.jwt_token:
            headers["Authorization"] = f"Bearer {self.jwt_token}"
        
        async with session.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
            headers=headers if headers else None
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def authenticate(self) -> bool:
        """
        获取 JWT Token
        
        需要: API Key + 钱包签名
        流程:
        1. 获取 auth message
        2. 用私钥签名
        3. 提交获取 JWT
        """
        if not self.private_key:
            print("❌ Predict.fun: 需要私钥进行认证")
            return False
        
        try:
            # 1. 获取 auth message
            auth_msg = await self._request(
                "GET", 
                "/auth/message",
                auth=False
            )
            message = auth_msg.get("message")
            
            # 2. 签名 (需要 web3)
            from web3 import Web3
            from eth_account.messages import encode_defunct
            
            w3 = Web3()
            account = w3.eth.account.from_key(self.private_key)
            
            message_encoded = encode_defunct(text=message)
            signed = account.sign_message(message_encoded)
            signature = signed.signature.hex()
            
            # 3. 获取 JWT
            jwt_response = await self._request(
                "POST",
                "/auth/jwt",
                json_data={
                    "message": message,
                    "signature": signature,
                    "address": account.address
                },
                auth=False
            )
            
            self.jwt_token = jwt_response.get("token")
            print(f"✅ Predict.fun: 认证成功")
            return True
            
        except Exception as e:
            print(f"❌ Predict.fun: 认证失败: {e}")
            return False
    
    async def get_all_markets(self) -> List[Market]:
        """获取所有活跃市场"""
        try:
            data = await self._request(
                "GET", 
                "/markets",
                params={"status": "active", "limit": 100}
            )
            
            markets = []
            for m in data.get("markets", []):
                market = self._parse_market(m)
                if market:
                    markets.append(market)
            
            return markets
            
        except Exception as e:
            print(f"❌ Predict.fun: 获取市场失败: {e}")
            return []
    
    def _parse_market(self, data: Dict) -> Optional[Market]:
        """解析市场数据"""
        try:
            # 解析价格
            yes_price = Decimal(str(data.get("yesPrice", 0.5)))
            no_price = Decimal(str(data.get("noPrice", 0.5)))
            
            # 解析时间
            expires_at = None
            if "endDate" in data:
                try:
                    expires_at = datetime.fromisoformat(data["endDate"].replace("Z", "+00:00"))
                except:
                    pass
            
            return Market(
                id=str(data.get("id", "")),
                slug=data.get("slug", ""),
                question=data.get("question") or data.get("title", "Unknown"),
                description=data.get("description", ""),
                category=data.get("category", ""),
                yes_price=yes_price,
                no_price=no_price,
                yes_token_id=data.get("yesTokenId"),
                no_token_id=data.get("noTokenId"),
                volume_24h=Decimal(str(data.get("volume24h", 0))),
                liquidity=Decimal(str(data.get("liquidity", 0))),
                expires_at=expires_at,
                active=data.get("status") == "active",
                raw_data=data
            )
        except Exception as e:
            print(f"⚠️ Predict.fun: 解析市场失败: {e}")
            return None
    
    async def get_market(self, market_id: str) -> Optional[Market]:
        """获取单个市场"""
        try:
            data = await self._request("GET", f"/markets/{market_id}")
            return self._parse_market(data)
        except Exception as e:
            print(f"❌ Predict.fun: 获取市场失败: {e}")
            return None
    
    async def get_prices(self, market_id: str) -> Dict[str, Decimal]:
        """获取市场价格"""
        market = await self.get_market(market_id)
        if market:
            return {
                "yes": market.yes_price,
                "no": market.no_price
            }
        return {"yes": Decimal("0.5"), "no": Decimal("0.5")}
    
    async def get_orderbook(self, market_id: str) -> Dict:
        """获取订单簿"""
        try:
            data = await self._request("GET", f"/markets/{market_id}/orderbook")
            
            return {
                "bids": [{"price": Decimal(str(b["price"])), "size": Decimal(str(b.get("size", 0)))} for b in data.get("bids", [])],
                "asks": [{"price": Decimal(str(a["price"])), "size": Decimal(str(a.get("size", 0)))} for a in data.get("asks", [])],
            }
        except Exception as e:
            print(f"❌ Predict.fun: 获取订单簿失败: {e}")
            return {"bids": [], "asks": []}
    
    async def build_buy_order(
        self,
        market_id: str,
        side: str,
        size: Decimal,
        price: Decimal
    ) -> Dict:
        """构建买入订单"""
        return {
            "platform": "predict_fun",
            "market_id": market_id,
            "side": side.lower(),
            "size": float(size),
            "price": float(price),
            "type": "limit"
        }
    
    async def send_order(self, order_data: Dict) -> Dict:
        """发送订单"""
        if not self.jwt_token:
            success = await self.authenticate()
            if not success:
                return {"success": False, "error": "认证失败"}
        
        try:
            payload = {
                "marketId": order_data["market_id"],
                "side": order_data["side"].upper(),
                "size": str(order_data["size"]),
                "price": str(order_data["price"]),
                "type": "LIMIT"
            }
            
            result = await self._request("POST", "/orders", json_data=payload)
            
            return {
                "success": True,
                "order_id": result.get("id"),
                "status": result.get("status"),
                "raw": result
            }
        except Exception as e:
            print(f"❌ Predict.fun: 下单失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            await self._request("DELETE", f"/orders/{order_id}")
            return True
        except Exception as e:
            print(f"❌ Predict.fun: 取消订单失败: {e}")
            return False
    
    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """获取订单列表"""
        try:
            params = {}
            if market_id:
                params["marketId"] = market_id
            
            data = await self._request("GET", "/orders", params=params)
            
            orders = []
            for o in data.get("orders", []):
                orders.append(Order(
                    id=str(o.get("id")),
                    market_id=str(o.get("marketId", "")),
                    side=o.get("side", "").lower(),
                    size=Decimal(str(o.get("size", 0))),
                    price=Decimal(str(o.get("price", 0))),
                    order_type=o.get("type", "limit").lower(),
                    status=o.get("status", "unknown").lower(),
                    raw_data=o
                ))
            
            return orders
        except Exception as e:
            print(f"❌ Predict.fun: 获取订单失败: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        try:
            data = await self._request("GET", "/positions")
            
            positions = []
            for p in data.get("positions", []):
                positions.append(Position(
                    market_id=str(p.get("marketId", "")),
                    side=p.get("side", "").lower(),
                    size=Decimal(str(p.get("size", 0))),
                    avg_price=Decimal(str(p.get("avgPrice", 0))),
                    current_price=Decimal(str(p.get("currentPrice", 0))),
                    pnl=Decimal(str(p.get("pnl", 0)))
                ))
            
            return positions
        except Exception as e:
            print(f"❌ Predict.fun: 获取持仓失败: {e}")
            return []
    
    async def get_balance(self) -> Dict[str, Decimal]:
        """获取账户余额"""
        try:
            data = await self._request("GET", "/account")
            
            return {
                "USDC": Decimal(str(data.get("balance", 0))),
                "locked": Decimal(str(data.get("lockedBalance", 0)))
            }
        except Exception as e:
            print(f"❌ Predict.fun: 获取余额失败: {e}")
            return {"USDC": Decimal("0"), "locked": Decimal("0")}
    
    async def close(self):
        """关闭连接"""
        if self._session and not self._session.closed:
            await self._session.close()
