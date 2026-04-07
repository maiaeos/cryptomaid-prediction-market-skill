"""
撸毛策略自动化
自动刷交易量、LP 挖矿、积分优化
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from platforms.base import PredictionMarket

logger = logging.getLogger(__name__)


@dataclass
class PointsTask:
    """积分任务"""
    name: str
    description: str
    points_reward: int
    completed: bool = False
    last_attempt: Optional[datetime] = None


class FarmingStrategy:
    """撸毛策略基类"""
    
    def __init__(self, platform: PredictionMarket, config: Dict):
        self.platform = platform
        self.config = config
        self.running = False
        
    async def run(self):
        """运行策略"""
        raise NotImplementedError
        
    def stop(self):
        """停止策略"""
        self.running = False


class VolumeFarming(FarmingStrategy):
    """
    交易量刷分策略
    
    在 tight spread 市场频繁买卖，赚取积分
    风险: 低（几乎无方向性风险）
    """
    
    def __init__(self, platform: PredictionMarket, config: Dict):
        super().__init__(platform, config)
        
        # 参数
        self.trade_size = Decimal(str(config.get("trade_size", 10)))  # 单笔金额
        self.min_spread = Decimal(str(config.get("min_spread", 0.005)))  # 最小 spread
        self.max_spread = Decimal(str(config.get("max_spread", 0.02)))  # 最大 spread
        self.interval = config.get("interval", 60)  # 交易间隔(秒)
        
        # 统计
        self.trades_count = 0
        self.volume_generated = Decimal("0")
        
    async def run(self):
        """运行刷量策略"""
        logger.info(f"🚀 启动交易量刷分策略 ({self.platform.name})")
        self.running = True
        
        while self.running:
            try:
                # 1. 寻找合适的市场
                market = await self._find_suitable_market()
                if not market:
                    logger.debug("未找到合适的市场，等待...")
                    await asyncio.sleep(self.interval)
                    continue
                
                # 2. 检查 spread
                spread = market.yes_price + market.no_price - Decimal("1")
                spread_pct = spread / Decimal("0.5")  # 相对于中间价
                
                if spread_pct < self.min_spread:
                    logger.debug(f"Spread 太小: {spread_pct:.4f}")
                    await asyncio.sleep(self.interval)
                    continue
                
                if spread_pct > self.max_spread:
                    logger.debug(f"Spread 太大: {spread_pct:.4f}")
                    await asyncio.sleep(self.interval)
                    continue
                
                # 3. 执行买卖 (同时下双边订单)
                logger.info(f"💰 执行刷量交易: {market.question[:50]}...")
                
                # 买 YES
                await self._place_order(market, "yes", market.yes_price)
                
                # 买 NO
                await self._place_order(market, "no", market.no_price)
                
                self.trades_count += 2
                self.volume_generated += self.trade_size * 2
                
                logger.info(f"📊 累计: {self.trades_count} 笔交易, {self.volume_generated} USDC 量")
                
                # 4. 等待
                await asyncio.sleep(self.interval)
                
            except Exception as e:
                logger.error(f"刷量策略错误: {e}")
                await asyncio.sleep(self.interval)
    
    async def _find_suitable_market(self) -> Optional[Dict]:
        """寻找适合刷量的市场"""
        markets = await self.platform.get_all_markets()
        
        # 筛选条件:
        # 1. 高流动性
        # 2. 接近 50/50 (spread 小)
        # 3. 活跃
        
        suitable = []
        for m in markets:
            if m.liquidity < 10000:  # 最小流动性
                continue
            
            # 价格接近 0.5 (最可能 tight spread)
            if abs(m.yes_price - Decimal("0.5")) > Decimal("0.2"):
                continue
            
            suitable.append(m)
        
        if not suitable:
            return None
        
        # 选择流动性最高的
        suitable.sort(key=lambda x: x.liquidity, reverse=True)
        return suitable[0]
    
    async def _place_order(self, market, side: str, price: Decimal):
        """下单"""
        try:
            order_data = await self.platform.build_buy_order(
                market_id=market.id,
                side=side,
                size=self.trade_size,
                price=price
            )
            
            result = await self.platform.send_order(order_data)
            
            if result.get("success"):
                logger.debug(f"✅ 下单成功: {side} @ {price}")
            else:
                logger.warning(f"❌ 下单失败: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"下单错误: {e}")


class LiquidityMining(FarmingStrategy):
    """
    流动性挖矿策略
    
    在订单簿两侧挂限价单，赚取 maker 返佣 + 积分
    要求: 较大的资金量
    """
    
    def __init__(self, platform: PredictionMarket, config: Dict):
        super().__init__(platform, config)
        
        # 参数
        self.quote_size = Decimal(str(config.get("quote_size", 100)))
        self.spread = Decimal(str(config.get("spread", 0.01)))
        self.refresh_interval = config.get("refresh_interval", 300)  # 5分钟刷新
        
        # 状态
        self.active_orders: Dict[str, Dict] = {}
        
    async def run(self):
        """运行流动性挖矿策略"""
        logger.info(f"🚀 启动流动性挖矿策略 ({self.platform.name})")
        self.running = True
        
        while self.running:
            try:
                # 1. 获取所有市场
                markets = await self.platform.get_all_markets()
                
                # 2. 筛选高流动性市场
                for market in markets:
                    if market.liquidity < 50000:
                        continue
                    
                    await self._provide_liquidity(market)
                
                # 3. 等待刷新
                await asyncio.sleep(self.refresh_interval)
                
                # 4. 刷新订单
                await self._refresh_orders()
                
            except Exception as e:
                logger.error(f"流动性挖矿错误: {e}")
                await asyncio.sleep(self.refresh_interval)
    
    async def _provide_liquidity(self, market):
        """为单个市场提供流动性"""
        try:
            # 获取订单簿
            orderbook = await self.platform.get_orderbook(market.id)
            
            if not orderbook.get("bids") or not orderbook.get("asks"):
                return
            
            best_bid = orderbook["bids"][0]["price"]
            best_ask = orderbook["asks"][0]["price"]
            mid = (best_bid + best_ask) / 2
            
            # 计算我们的报价
            our_bid = mid - self.spread / 2
            our_ask = mid + self.spread / 2
            
            # 确保比当前最佳价格更差 (避免被吃)
            if our_bid > best_bid:
                our_bid = best_bid - Decimal("0.005")
            if our_ask < best_ask:
                our_ask = best_ask + Decimal("0.005")
            
            # 下单
            bid_order = await self.platform.build_buy_order(
                market_id=market.id,
                side="yes",
                size=self.quote_size,
                price=our_bid
            )
            
            ask_order = await self.platform.build_buy_order(
                market_id=market.id,
                side="no",
                size=self.quote_size,
                price=our_ask
            )
            
            # 发送订单
            bid_result = await self.platform.send_order(bid_order)
            ask_result = await self.platform.send_order(ask_order)
            
            # 记录
            if bid_result.get("success"):
                self.active_orders[bid_result["order_id"]] = {
                    "market_id": market.id,
                    "side": "yes",
                    "price": our_bid
                }
            
            if ask_result.get("success"):
                self.active_orders[ask_result["order_id"]] = {
                    "market_id": market.id,
                    "side": "no",
                    "price": our_ask
                }
            
            logger.info(f"💧 提供流动性: {market.slug} - Bid {our_bid} / Ask {our_ask}")
            
        except Exception as e:
            logger.error(f"提供流动性错误: {e}")
    
    async def _refresh_orders(self):
        """刷新所有订单"""
        logger.info(f"🔄 刷新 {len(self.active_orders)} 个订单")
        
        # 取消所有旧订单
        for order_id in list(self.active_orders.keys()):
            try:
                await self.platform.cancel_order(order_id)
            except:
                pass
        
        self.active_orders.clear()


class PointsTracker:
    """积分追踪器"""
    
    def __init__(self, platform: PredictionMarket):
        self.platform = platform
        self.points_history: List[Dict] = []
        
    async def get_current_points(self) -> Dict:
        """获取当前积分"""
        try:
            balance = await self.platform.get_balance()
            return {
                "points": balance.get("points", Decimal("0")),
                "timestamp": datetime.now()
            }
        except Exception as e:
            logger.error(f"获取积分失败: {e}")
            return {"points": Decimal("0"), "timestamp": datetime.now()}
    
    async def track(self):
        """定期追踪积分"""
        while True:
            try:
                points = await self.get_current_points()
                self.points_history.append(points)
                
                # 只保留最近 30 天
                cutoff = datetime.now() - timedelta(days=30)
                self.points_history = [
                    p for p in self.points_history 
                    if p["timestamp"] > cutoff
                ]
                
                logger.info(f"📊 当前积分: {points['points']}")
                
                await asyncio.sleep(3600)  # 每小时记录一次
                
            except Exception as e:
                logger.error(f"积分追踪错误: {e}")
                await asyncio.sleep(3600)
    
    def get_points_growth(self, days: int = 7) -> Decimal:
        """获取积分增长"""
        if len(self.points_history) < 2:
            return Decimal("0")
        
        cutoff = datetime.now() - timedelta(days=days)
        recent = [p for p in self.points_history if p["timestamp"] > cutoff]
        
        if len(recent) < 2:
            return Decimal("0")
        
        return recent[-1]["points"] - recent[0]["points"]


class FarmingOrchestrator:
    """撸毛策略编排器"""
    
    def __init__(self, platforms: Dict[str, PredictionMarket], config: Dict):
        self.platforms = platforms
        self.config = config
        self.strategies: List[FarmingStrategy] = []
        self.trackers: Dict[str, PointsTracker] = {}
        
    def add_volume_farming(self, platform_name: str, strategy_config: Dict):
        """添加刷量策略"""
        if platform_name not in self.platforms:
            logger.error(f"平台不存在: {platform_name}")
            return
        
        strategy = VolumeFarming(self.platforms[platform_name], strategy_config)
        self.strategies.append(strategy)
        
    def add_liquidity_mining(self, platform_name: str, strategy_config: Dict):
        """添加流动性挖矿策略"""
        if platform_name not in self.platforms:
            logger.error(f"平台不存在: {platform_name}")
            return
        
        strategy = LiquidityMining(self.platforms[platform_name], strategy_config)
        self.strategies.append(strategy)
    
    def start_tracking(self):
        """启动积分追踪"""
        for name, platform in self.platforms.items():
            tracker = PointsTracker(platform)
            self.trackers[name] = tracker
            asyncio.create_task(tracker.track())
    
    async def run_all(self):
        """运行所有策略"""
        logger.info("🚀 启动所有撸毛策略")
        
        # 启动积分追踪
        self.start_tracking()
        
        # 并行运行所有策略
        tasks = [asyncio.create_task(s.run()) for s in self.strategies]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def stop_all(self):
        """停止所有策略"""
        logger.info("🛑 停止所有撸毛策略")
        for strategy in self.strategies:
            strategy.stop()
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "strategies_running": len([s for s in self.strategies if s.running]),
            "total_strategies": len(self.strategies),
            "trackers": {name: t.points_history[-1] if t.points_history else None 
                        for name, t in self.trackers.items()}
        }
