"""
Limitless 交易接口完整实现
支持真实下单、取消、查询
"""

import aiohttp
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from platforms.base import PredictionMarket, Market, Order, Position


class LimitlessAPI:
    """Limitless API 客户端"""
    
    BASE_URL = "https://api.limitless.exchange"
    
    def __init__(self, api_key: str, wallet_address: str):
        self.api_key = api_key
        self.wallet_address = wallet_address.lower()
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP session"""
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
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"API 错误 {resp.status}: {text}")
            
            return await resp.json()
    
    # ========== 市场数据 ==========
    
    async def get_markets(self, status: str = "active") -> List[Dict]:
        """获取市场列表"""
        return await self._request("GET", "/markets/active")
    
    async def get_market(self, market_id: str) -> Dict:
        """获取单个市场"""
        return await self._request("GET", f"/markets/{market_id}")
    
    async def get_orderbook(self, market_id: str) -> Dict:
        """获取订单簿"""
        return await self._request("GET", f"/markets/{market_id}/orderbook")
    
    # ========== 交易接口 ==========
    
    async def create_order(
        self,
        market_id: str,
        side: str,  # "yes" or "no"
        size: Decimal,
        price: Decimal,
        order_type: str = "limit"
    ) -> Dict:
        """
        创建订单
        
        Args:
            market_id: 市场 ID
            side: "yes" 或 "no"
            size: 交易数量
            price: 价格 (0-1)
            order_type: "limit" 或 "market"
        """
        data = {
            "marketId": market_id,
            "side": side.upper(),
            "size": str(size),
            "price": str(price),
            "type": order_type.upper(),
            "walletAddress": self.wallet_address
        }
        
        return await self._request("POST", "/orders", json_data=data)
    
    async def cancel_order(self, order_id: str) -> Dict:
        """取消订单"""
        return await self._request(
            "DELETE",
            f"/orders/{order_id}",
            json_data={"walletAddress": self.wallet_address}
        )
    
    async def get_orders(self, market_id: Optional[str] = None) -> List[Dict]:
        """获取订单列表"""
        params = {"walletAddress": self.wallet_address}
        if market_id:
            params["marketId"] = market_id
        return await self._request("GET", "/orders", params=params)
    
    async def get_order(self, order_id: str) -> Dict:
        """获取订单详情"""
        return await self._request("GET", f"/orders/{order_id}")
    
    # ========== 账户接口 ==========
    
    async def get_balance(self) -> Dict:
        """获取账户余额"""
        return await self._request(
            "GET",
            "/account/balance",
            params={"walletAddress": self.wallet_address}
        )
    
    async def get_positions(self) -> List[Dict]:
        """获取持仓"""
        return await self._request(
            "GET",
            "/account/positions",
            params={"walletAddress": self.wallet_address}
        )
    
    async def close(self):
        """关闭 session"""
        if self._session and not self._session.closed:
            await self._session.close()


class LimitlessPlatform(PredictionMarket):
    """Limitless 平台完整实现"""
    
    def __init__(self, api_key: str, wallet_address: str, wallet=None):
        super().__init__("limitless")
        self.api = LimitlessAPI(api_key, wallet_address)
        self.wallet = wallet  # 可选，用于签名
    
    # ========== 市场数据 ==========
    
    async def get_all_markets(self) -> List[Market]:
        """获取所有活跃市场"""
        data = await self.api.get_markets(status="active")
        
        # 处理可能的返回格式
        if isinstance(data, dict) and "data" in data:
            markets_data = data["data"]
        elif isinstance(data, list):
            markets_data = data
        else:
            markets_data = data.get("markets", [])
        
        markets = []
        for m in markets_data:
            try:
                # 解析价格 (prices 数组 [yes, no])
                prices = m.get("prices", [50, 50])
                yes_price = Decimal(str(prices[0])) / 100 if len(prices) > 0 else Decimal("0.5")
                no_price = Decimal(str(prices[1])) / 100 if len(prices) > 1 else Decimal("0.5")
                
                market = Market(
                    id=str(m.get("id", "")),
                    slug=m.get("slug", ""),
                    question=m.get("title", ""),
                    description=m.get("description", ""),
                    category=",".join(m.get("categories", [])),
                    yes_price=yes_price,
                    no_price=no_price,
                    yes_token_id=m.get("positionIds", [None, None])[0] if m.get("positionIds") else None,
                    no_token_id=m.get("positionIds", [None, None])[1] if m.get("positionIds") else None,
                    volume_24h=Decimal(str(m.get("volumeFormatted", 0))),
                    liquidity=Decimal(str(m.get("liquidityFormatted", 0))),
                    expires_at=datetime.fromtimestamp(m.get("expirationTimestamp", 0) / 1000) if m.get("expirationTimestamp") else None,
                    raw_data=m
                )
                markets.append(market)
            except Exception as e:
                print(f"⚠️ 解析市场失败: {e}")
                continue
        
        return markets
    
    async def get_market(self, market_id: str) -> Optional[Market]:
        """获取单个市场"""
        try:
            data = await self.api.get_market(market_id)
            m = data.get("market", {})
            
            return Market(
                id=m["id"],
                slug=m.get("slug", ""),
                question=m["question"],
                yes_price=Decimal(str(m.get("yesPrice", 0.5))),
                no_price=Decimal(str(m.get("noPrice", 0.5))),
                volume_24h=Decimal(str(m.get("volume24h", 0))),
                liquidity=Decimal(str(m.get("liquidity", 0))),
                raw_data=m
            )
        except:
            return None
    
    async def get_prices(self, market_id: str) -> Dict[str, Decimal]:
        """获取价格"""
        market = await self.get_market(market_id)
        if market:
            return {
                "yes": market.yes_price,
                "no": market.no_price
            }
        return {"yes": Decimal("0"), "no": Decimal("0")}
    
    async def get_orderbook(self, market_id: str) -> Dict:
        """获取订单簿"""
        data = await self.api.get_orderbook(market_id)
        
        return {
            "bids": [
                {"price": Decimal(str(b["price"])), "size": Decimal(str(b["size"]))}
                for b in data.get("bids", [])
            ],
            "asks": [
                {"price": Decimal(str(a["price"])), "size": Decimal(str(a["size"]))}
                for a in data.get("asks", [])
            ]
        }
    
    # ========== 交易接口 ==========
    
    async def build_buy_order(
        self,
        market_id: str,
        side: str,
        size: Decimal,
        price: Decimal
    ) -> Dict:
        """构建买单"""
        return {
            "market_id": market_id,
            "side": side,
            "size": size,
            "price": price,
            "type": "limit",
            "platform": "limitless"
        }
    
    async def send_order(self, order_data: Dict) -> Dict:
        """发送订单"""
        try:
            result = await self.api.create_order(
                market_id=order_data["market_id"],
                side=order_data["side"],
                size=order_data["size"],
                price=order_data["price"],
                order_type=order_data.get("type", "limit")
            )
            
            return {
                "success": True,
                "order_id": result.get("orderId"),
                "status": result.get("status"),
                "raw": result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        try:
            await self.api.cancel_order(order_id)
            return True
        except:
            return False
    
    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """获取订单列表"""
        data = await self.api.get_orders(market_id)
        
        orders = []
        for o in data.get("orders", []):
            orders.append(Order(
                id=o["id"],
                market_id=o.get("marketId", ""),
                side=o.get("side", "").lower(),
                size=Decimal(str(o.get("size", 0))),
                price=Decimal(str(o.get("price", 0))),
                status=o.get("status", "pending").lower(),
                filled_size=Decimal(str(o.get("filledSize", 0))),
                remaining_size=Decimal(str(o.get("remainingSize", 0))),
                raw_data=o
            ))
        
        return orders
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """获取单个订单"""
        try:
            data = await self.api.get_order(order_id)
            o = data.get("order", {})
            
            return Order(
                id=o["id"],
                market_id=o.get("marketId", ""),
                side=o.get("side", "").lower(),
                size=Decimal(str(o.get("size", 0))),
                price=Decimal(str(o.get("price", 0))),
                status=o.get("status", "").lower(),
                filled_size=Decimal(str(o.get("filledSize", 0))),
                remaining_size=Decimal(str(o.get("remainingSize", 0))),
                raw_data=o
            )
        except:
            return None
    
    # ========== 账户接口 ==========
    
    async def get_positions(self) -> List[Position]:
        """获取持仓"""
        data = await self.api.get_positions()
        
        positions = []
        for p in data.get("positions", []):
            positions.append(Position(
                market_id=p.get("marketId", ""),
                side=p.get("side", "").lower(),
                size=Decimal(str(p.get("size", 0))),
                avg_price=Decimal(str(p.get("avgPrice", 0))),
                current_price=Decimal(str(p.get("currentPrice", 0))),
                pnl=Decimal(str(p.get("pnl", 0)))
            ))
        
        return positions
    
    async def get_balance(self) -> Dict[str, Decimal]:
        """获取余额"""
        data = await self.api.get_balance()
        
        return {
            "USDC": Decimal(str(data.get("usdcBalance", 0))),
            "points": Decimal(str(data.get("points", 0)))
        }
    
    async def close(self):
        """关闭连接"""
        await self.api.close()
