"""
预测市场平台基类
定义统一接口，所有平台必须实现
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Market:
    """统一的市场数据结构"""
    id: str
    slug: str
    question: str
    description: str = ""
    category: str = ""
    
    # 价格
    yes_price: Decimal = Decimal("0.5")
    no_price: Decimal = Decimal("0.5")
    
    # Token ID (用于交易)
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    
    # 流动性
    volume_24h: Decimal = Decimal("0")
    liquidity: Decimal = Decimal("0")
    
    # 时间
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # 状态
    active: bool = True
    resolved: bool = False
    
    # 原始数据
    raw_data: Dict = None
    
    def __post_init__(self):
        if self.raw_data is None:
            self.raw_data = {}
    
    @property
    def spread(self) -> Decimal:
        """买卖价差 (应该接近 0)"""
        return self.yes_price + self.no_price - Decimal("1")
    
    @property
    def implied_probability(self) -> Decimal:
        """隐含概率"""
        return self.yes_price


@dataclass
class Order:
    """统一的订单数据结构"""
    id: Optional[str] = None
    market_id: str = ""
    side: str = ""  # "yes" or "no"
    size: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    order_type: str = "limit"  # "limit" or "market"
    status: str = "pending"  # "pending", "open", "filled", "cancelled"
    created_at: Optional[datetime] = None
    filled_size: Decimal = Decimal("0")
    remaining_size: Decimal = Decimal("0")
    
    # 原始数据
    raw_data: Dict = None
    
    def __post_init__(self):
        if self.raw_data is None:
            self.raw_data = {}


@dataclass
class Position:
    """统一的持仓数据结构"""
    market_id: str = ""
    side: str = ""  # "yes" or "no"
    size: Decimal = Decimal("0")
    avg_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")
    
    @property
    def market_value(self) -> Decimal:
        """当前市值"""
        return self.size * self.current_price


class PredictionMarket(ABC):
    """预测市场平台基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.enabled = True
    
    @abstractmethod
    async def get_all_markets(self) -> List[Market]:
        """获取所有活跃市场"""
        pass
    
    @abstractmethod
    async def get_market(self, market_id: str) -> Optional[Market]:
        """获取单个市场详情"""
        pass
    
    @abstractmethod
    async def get_prices(self, market_id: str) -> Dict[str, Decimal]:
        """
        获取市场价格
        返回: {"yes": Decimal, "no": Decimal}
        """
        pass
    
    async def get_all_prices(self) -> List[Market]:
        """
        获取所有市场的价格
        默认实现: 获取所有市场并填充价格
        子类可以覆盖以提高效率
        """
        markets = await self.get_all_markets()
        result = []
        
        for market in markets:
            try:
                prices = await self.get_prices(market.id)
                market.yes_price = prices.get("yes", market.yes_price)
                market.no_price = prices.get("no", market.no_price)
                result.append(market)
            except Exception as e:
                print(f"⚠️ {self.name}: 获取 {market.id} 价格失败: {e}")
                continue
        
        return result
    
    @abstractmethod
    async def get_orderbook(self, market_id: str) -> Dict:
        """
        获取订单簿
        返回: {
            "bids": [{"price": Decimal, "size": Decimal}, ...],
            "asks": [{"price": Decimal, "size": Decimal}, ...]
        }
        """
        pass
    
    @abstractmethod
    async def build_buy_order(
        self,
        market_id: str,
        side: str,  # "yes" or "no"
        size: Decimal,
        price: Decimal
    ) -> Dict:
        """
        构建买入订单
        返回: 未签名的交易数据
        """
        pass
    
    @abstractmethod
    async def send_order(self, signed_tx: Dict) -> Dict:
        """
        发送已签名的订单
        返回: 订单结果
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        pass
    
    @abstractmethod
    async def get_orders(self, market_id: Optional[str] = None) -> List[Order]:
        """获取订单列表"""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """获取持仓列表"""
        pass
    
    @abstractmethod
    async def get_balance(self) -> Dict[str, Decimal]:
        """
        获取账户余额
        返回: {"USDC": Decimal, ...}
        """
        pass
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            markets = await self.get_all_markets()
            return len(markets) > 0
        except Exception as e:
            print(f"❌ {self.name} 健康检查失败: {e}")
            return False
