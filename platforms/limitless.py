"""
Limitless Exchange 平台集成
使用官方 REST API
"""

import aiohttp
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from .base import PredictionMarket, Market, Order, Position


class LimitlessPlatform(PredictionMarket):
    """Limitless Exchange 平台实现"""
    
    BASE_URL = "https://api.limitless.exchange"
    
    def __init__(self, api_key: str, account_address: Optional[str] = None):
        super().__init__("limitless")
        self.api_key = api_key
        self.account_address = account_address
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        return self._session
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict:
        """发送 API 请求"""
        session = await self._get_session()
        url = f"{self.BASE_URL}{endpoint}"
        
        async with session.request(
            method=method,
            url=url,
            params=params,
            json=json_data
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def get_all_markets(self) -> List[Market]:
        """获取所有活跃市场"""
        data = await self._request("GET", "/markets/active")
        
        # 处理可能的返回格式
        if isinstance(data, dict) and "data" in data:
            markets_data = data["data"]
        elif isinstance(data, list):
            markets_data = data
        else:
            markets_data = data.get("markets", [])
        
        markets = []
        for m in markets_data:
            market = self._parse_market(m)
            if market:
                markets.append(market)
        
        return markets
    
    def _parse_market(self, data: Dict) -> Optional[Market]:
        """解析市场数据"""
        try:
            # 解析价格 (Limitless 返回 prices 数组 [yes, no])
            prices = data.get("prices", [50, 50])
            if isinstance(prices, list) and len(prices) >= 2:
                yes_price = Decimal(str(prices[0])) / Decimal("100")
                no_price = Decimal(str(prices[1])) / Decimal("100")
            else:
                yes_price = Decimal("0.5")
                no_price = Decimal("0.5")
            
            # 解析时间
            expires_at = None
            if "endDate" in data:
                try:
                    expires_at = datetime.fromisoformat(data["endDate"].replace("Z", "+00:00"))
                except:
                    pass
            
            return Market(
                id=data.get("id", data.get("slug", "")),
                slug=data.get("slug", ""),
                question=data.get("title") or data.get("question", "Unknown"),
                description=data.get("description", ""),
                category=data.get("category", ""),
                yes_price=yes_price,
                no_price=no_price,
                volume_24h=Decimal(str(data.get("volume", 0))),
                liquidity=Decimal(str(data.get("liquidity", 0))),
                expires_at=expires_at,
                active=data.get("status") == "active",
                raw_data=data
            )
        except Exception as e:
            print(f"⚠️ Limitless: 解析市场失败: {e}")
            return None
    
    async def get_market(self, market_id: str) -> Optional[Market]:
        """获取单个市场详情"""
        try:
            data = await self._request("GET", f"/markets/{market_id}")
            return self._parse_market(data)
        except Exception as e:
            print(f"❌ Limitless: 获取市场 {market_id} 失败: {e}")
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
            
            # 解析订单簿
            yes_bids = data.get("yesBids", [])
            yes_asks = data.get("yesAsks", [])
            no_bids = data.get("noBids", [])
            no_asks = data.get("noAsks", [])
            
            return {
                "yes_bids": [{"price": Decimal(str(b["price"])), "size": Decimal(str(b.get("size", 0)))} for b in yes_bids],
                "yes_asks": [{"price": Decimal(str(a["price"])), "size": Decimal(str(a.get("size", 0)))} for a in yes_asks],
                "no_bids": [{"price": Decimal(str(b["price"])), "size": Decimal(str(b.get("size", 0)))} for b in no_bids],
                "no_asks": [{"price": Decimal(str(a["price"])), "size": Decimal(str(a.get("size", 0)))} for a in no_asks],
            }
        except Exception as e:
            print(f"❌ Limitless: 获取订单簿失败: {e}")
            return {"yes_bids": [], "yes_asks": [], "no_bids": [], "no_asks": []}
    
    async def build_buy_order(
        self,
        market_id: str,
        side: str,
        size: Decimal,
        price: Decimal
    ) -> Dict:
        """
        构建买入订单
        Limitless 使用 REST API 直接下单，不需要预构建交易
        """
        return {
            "platform": "limitless",
            "market_id": market_id,
            "side": side.lower(),
            "size": float(size),
            "price": float(price),
            "type": "limit"
        }
    
    async def send_order(self, order_data: Dict) -> Dict:
        """发送订单"""
        try:
            # 获取市场详情以获取内部 ID
            market = await self.get_market(order_data["market_id"])
            if not market:
                raise ValueError(f"市场不存在: {order_data['market_id']}")
            
            payload = {
                "marketId": market.id,
                "side": order_data["side"],
                "size": order_data["size"],
                "price": order_data["price"],
                "type": "limit"
            }
            
            result = await self._request("POST", "/orders", json_data=payload)
            
            return {
                "success": True,
                "order_id": result.get("orderId"),
                "status": result.get("status"),
                "raw": result
            }
        except Exception as e:
            print(f"❌ Limitless: 下单失败: {e}")
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
            print(f"❌ Limitless: 取消订单失败: {e}")
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
                    id=o.get("orderId"),
                    market_id=o.get("marketId", ""),
                    side=o.get("side", ""),
                    size=Decimal(str(o.get("size", 0))),
                    price=Decimal(str(o.get("price", 0))),
                    order_type=o.get("type", "limit"),
                    status=o.get("status", "unknown"),
                    raw_data=o
                ))
            
            return orders
        except Exception as e:
            print(f"❌ Limitless: 获取订单失败: {e}")
            return []
    
    async def get_positions(self) -> List[Position]:
        """获取持仓列表"""
        try:
            params = {}
            if self.account_address:
                params["account"] = self.account_address
            
            data = await self._request("GET", "/portfolio/positions", params=params)
            
            positions = []
            for p in data if isinstance(data, list) else data.get("positions", []):
                positions.append(Position(
                    market_id=p.get("marketId", ""),
                    side=p.get("side", ""),
                    size=Decimal(str(p.get("size", 0))),
                    avg_price=Decimal(str(p.get("avgPrice", 0))),
                    current_price=Decimal(str(p.get("currentPrice", 0))),
                    pnl=Decimal(str(p.get("pnl", 0)))
                ))
            
            return positions
        except Exception as e:
            print(f"❌ Limitless: 获取持仓失败: {e}")
            return []
    
    async def get_balance(self) -> Dict[str, Decimal]:
        """获取账户余额"""
        try:
            # Limitless API 没有直接的余额端点，从 profile 获取
            data = await self._request("GET", "/profile")
            
            return {
                "USDC": Decimal(str(data.get("balance", 0))),
                "points": Decimal(str(data.get("points", 0)))
            }
        except Exception as e:
            print(f"❌ Limitless: 获取余额失败: {e}")
            return {"USDC": Decimal("0"), "points": Decimal("0")}
    
    async def close(self):
        """关闭连接"""
        if self._session and not self._session.closed:
            await self._session.close()
