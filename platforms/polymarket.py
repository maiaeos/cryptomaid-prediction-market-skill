"""
Polymarket 平台集成
直接和合约交互，不使用官方 API
"""

import json
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

from .base import PredictionMarket, Market, Order, Position


# Polymarket 合约地址 (Polygon)
CONTRACTS = {
    "usdc": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",  # USDC.e
    "ctf": "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045",   # Conditional Tokens
    "exchange": "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",  # CTF Exchange
    "neg_risk_exchange": "0xC5d563A36AE78145C45a50134d48A1215220f80a",
    "neg_risk_adapter": "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
}

# 简化 ABI (只包含需要的函数)
USDC_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]

CTF_ABI = [
    {"constant": True, "inputs": [{"name": "account", "type": "address"}, {"name": "id", "type": "uint256"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]


class PolymarketPlatform(PredictionMarket):
    """Polymarket 平台实现 - 直接合约交互"""
    
    GAMMA_API = "https://gamma-api.polymarket.com"
    CLOB_API = "https://clob.polymarket.com"
    
    def __init__(self, rpc_url: str, private_key: str, funder_address: Optional[str] = None):
        super().__init__("polymarket")
        
        # Web3 连接
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError("无法连接到 Polygon RPC")
        
        # 账户
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.funder_address = funder_address or self.address
        
        # 合约实例
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(CONTRACTS["usdc"]),
            abi=USDC_ABI
        )
        self.ctf = self.w3.eth.contract(
            address=Web3.to_checksum_address(CONTRACTS["ctf"]),
            abi=CTF_ABI
        )
    
    async def get_all_markets(self) -> List[Market]:
        """从 Gamma API 获取所有活跃市场"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.GAMMA_API}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "liquidityMin": "1000",
                    "limit": "100"
                }
            ) as response:
                data = await response.json()
        
        markets = []
        for m in data if isinstance(data, list) else data.get("markets", []):
            market = self._parse_market(m)
            if market:
                markets.append(market)
        
        return markets
    
    def _parse_market(self, data: Dict) -> Optional[Market]:
        """解析市场数据"""
        try:
            # 获取 outcomes 价格
            outcomes = data.get("outcomes", [])
            if len(outcomes) >= 2:
                yes_price = Decimal(str(outcomes[0].get("price", 0))) / Decimal("100")
                no_price = Decimal(str(outcomes[1].get("price", 0))) / Decimal("100")
            else:
                yes_price = Decimal(str(data.get("yesPrice", 0.5)))
                no_price = Decimal(str(data.get("noPrice", 0.5)))
            
            # 获取 token IDs
            token_ids = data.get("clobTokenIds", [])
            yes_token_id = token_ids[0] if len(token_ids) > 0 else None
            no_token_id = token_ids[1] if len(token_ids) > 1 else None
            
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
                question=data.get("question") or data.get("title", "Unknown"),
                description=data.get("description", ""),
                category=data.get("category", ""),
                yes_price=yes_price,
                no_price=no_price,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
                volume_24h=Decimal(str(data.get("volume24hr", 0))),
                liquidity=Decimal(str(data.get("liquidity", 0))),
                expires_at=expires_at,
                active=data.get("active", True),
                raw_data=data
            )
        except Exception as e:
            print(f"⚠️ Polymarket: 解析市场失败: {e}")
            return None
    
    async def get_market(self, market_id: str) -> Optional[Market]:
        """获取单个市场"""
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.GAMMA_API}/markets/{market_id}") as response:
                data = await response.json()
                return self._parse_market(data)
    
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
        """从 CLOB API 获取订单簿"""
        import aiohttp
        
        # 获取市场以获取 token ID
        market = await self.get_market(market_id)
        if not market or not market.yes_token_id:
            return {"bids": [], "asks": []}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.CLOB_API}/book",
                params={"token_id": market.yes_token_id}
            ) as response:
                data = await response.json()
        
        # 解析订单簿
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        
        return {
            "bids": [{"price": Decimal(b["price"]), "size": Decimal(b.get("size", 0))} for b in bids],
            "asks": [{"price": Decimal(a["price"]), "size": Decimal(a.get("size", 0))} for a in asks],
        }
    
    async def build_buy_order(
        self,
        market_id: str,
        side: str,
        size: Decimal,
        price: Decimal
    ) -> Dict:
        """
        构建买入订单 (EIP-712 签名)
        
        Polymarket 使用 CLOB 订单簿，需要构建 EIP-712 签名订单
        """
        market = await self.get_market(market_id)
        if not market:
            raise ValueError(f"市场不存在: {market_id}")
        
        token_id = market.yes_token_id if side.lower() == "yes" else market.no_token_id
        if not token_id:
            raise ValueError(f"无法获取 {side} token ID")
        
        # 构建订单数据
        # 注意: 这是简化版本，实际需要完整的 EIP-712 结构
        order_data = {
            "platform": "polymarket",
            "type": "order",
            "token_id": token_id,
            "side": "BUY" if side.lower() == "yes" else "SELL",
            "size": float(size),
            "price": float(price),
            "maker": self.address,
            "taker": "0x0000000000000000000000000000000000000000",  # 任意 taker
            "expiration": int(datetime.now().timestamp()) + 86400,  # 1天后过期
            "nonce": int(datetime.now().timestamp() * 1000),
            "chain_id": 137,  # Polygon
        }
        
        return order_data
    
    async def send_order(self, signed_order: Dict) -> Dict:
        """发送签名订单到 CLOB"""
        import aiohttp
        
        # 这里需要实现完整的 CLOB 订单提交
        # 简化版本，实际需要调用 CLOB API
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.CLOB_API}/order",
                json=signed_order
            ) as response:
                result = await response.json()
                
                return {
                    "success": response.status == 200,
                    "order_id": result.get("orderId"),
                    "status": result.get("status"),
                    "raw": result
                }
    
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        # 需要构建取消订单的签名
        print(f"⚠️ Polymarket: 取消订单需要实现签名")
        return False
    
    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """获取订单列表"""
        # 需要从 CLOB API 获取
        print(f"⚠️ Polymarket: get_orders 需要 CLOB API 认证")
        return []
    
    async def get_positions(self) -> List[Position]:
        """获取持仓 (查询 CTF 合约)"""
        positions = []
        
        # 获取所有市场
        markets = await self.get_all_markets()
        
        for market in markets:
            if not market.yes_token_id:
                continue
            
            try:
                # 查询 YES token 余额
                yes_balance = self.ctf.functions.balanceOf(
                    Web3.to_checksum_address(self.address),
                    int(market.yes_token_id)
                ).call()
                
                if yes_balance > 0:
                    positions.append(Position(
                        market_id=market.id,
                        side="yes",
                        size=Decimal(yes_balance) / Decimal("1000000"),  # USDC 6位小数
                        avg_price=market.yes_price,  # 简化，实际需要计算
                        current_price=market.yes_price,
                    ))
                
                # 查询 NO token 余额
                if market.no_token_id:
                    no_balance = self.ctf.functions.balanceOf(
                        Web3.to_checksum_address(self.address),
                        int(market.no_token_id)
                    ).call()
                    
                    if no_balance > 0:
                        positions.append(Position(
                            market_id=market.id,
                            side="no",
                            size=Decimal(no_balance) / Decimal("1000000"),
                            avg_price=market.no_price,
                            current_price=market.no_price,
                        ))
            
            except Exception as e:
                print(f"⚠️ Polymarket: 查询持仓失败 {market.id}: {e}")
                continue
        
        return positions
    
    async def get_balance(self) -> Dict[str, Decimal]:
        """获取 USDC 余额"""
        try:
            balance = self.usdc.functions.balanceOf(
                Web3.to_checksum_address(self.address)
            ).call()
            
            return {
                "USDC": Decimal(balance) / Decimal("1000000"),  # USDC 6位小数
                "MATIC": Decimal(self.w3.eth.get_balance(self.address)) / Decimal("10")**18
            }
        except Exception as e:
            print(f"❌ Polymarket: 获取余额失败: {e}")
            return {"USDC": Decimal("0"), "MATIC": Decimal("0")}
