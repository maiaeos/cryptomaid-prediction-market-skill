"""
防狙击做市策略
遵循原则: 小单、随机、不暴露模式
"""

import asyncio
import random
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from platforms.base import PredictionMarket
from farming_strategies import FarmingStrategy

logger = logging.getLogger(__name__)


class AntiSnipeMarketMaker(FarmingStrategy):
    """
    防狙击做市策略
    
    核心原则:
    1. 小单分散 - 避免大单被狙击
    2. 随机化 - 时间、价格、数量都随机
    3. 不暴露模式 - 不固定间隔，不固定价格
    4. 快速撤单 - 订单不长期挂盘
    """
    
    def __init__(self, platform: PredictionMarket, config: Dict):
        super().__init__(platform, config)
        
        # 基础参数
        self.base_trade_size = Decimal(str(config.get("base_trade_size", 10)))
        self.max_trade_size = Decimal(str(config.get("max_trade_size", 50)))
        self.min_interval = config.get("min_interval", 30)  # 最小间隔
        self.max_interval = config.get("max_interval", 120)  # 最大间隔
        
        # 防狙击参数
        self.order_lifetime = config.get("order_lifetime", 60)  # 订单存活时间
        self.price_variance = Decimal(str(config.get("price_variance", 0.005)))  # 价格随机范围
        self.size_variance = Decimal(str(config.get("size_variance", 0.2)))  # 数量随机范围
        
        # 自动暂停参数
        self.snipe_pause_threshold = config.get("snipe_pause_threshold", 5)  # 被狙击次数阈值
        self.snipe_pause_duration = config.get("snipe_pause_duration", 600)  # 暂停时长(秒)
        self.min_trades_for_check = config.get("min_trades_for_check", 10)  # 最小交易数才检查
        
        # 成本监控参数
        self.max_gas_cost_usd = Decimal(str(config.get("max_gas_cost_usd", 1.0)))  # 最大Gas成本
        self.min_profit_margin = Decimal(str(config.get("min_profit_margin", 0.002)))  # 最小利润边际 0.2%
        
        # 状态
        self.is_paused = False
        self.pause_until = None
        self.total_gas_cost = Decimal("0")
        self.estimated_profit = Decimal("0")
        
        # 统计
        self.stats = {
            "trades": 0,
            "volume": Decimal("0"),
            "sniped_count": 0,
            "cancelled_count": 0,
            "paused_count": 0,
            "skipped_for_cost": 0
        }
    
    def _randomize_size(self) -> Decimal:
        """随机化交易金额"""
        variance = random.uniform(-float(self.size_variance), float(self.size_variance))
        size = self.base_trade_size * (1 + Decimal(str(variance)))
        # 限制范围
        size = max(self.base_trade_size * Decimal("0.5"), min(size, self.max_trade_size))
        return size.quantize(Decimal("0.01"))
    
    def _randomize_interval(self) -> int:
        """随机化间隔时间"""
        return random.randint(self.min_interval, self.max_interval)
    
    def _randomize_price(self, base_price: Decimal) -> Decimal:
        """随机化价格"""
        variance = random.uniform(-float(self.price_variance), float(self.price_variance))
        price = base_price * (1 + Decimal(str(variance)))
        return price.quantize(Decimal("0.001"))
    
    async def _place_snipe_resistant_order(self, market, side: str, base_price: Decimal):
        """
        下防狙击订单
        
        策略:
        1. 随机化订单大小
        2. 随机化价格 (略微偏离最优价)
        3. 设置订单过期时间
        4. 监控是否被狙击
        """
        # 随机化参数
        size = self._randomize_size()
        price = self._randomize_price(base_price)
        
        logger.info(f"📊 下单: {side} {size} @ {price} (随机化)")
        
        try:
            # 构建订单
            order_data = await self.platform.build_buy_order(
                market_id=market.id,
                side=side,
                size=size,
                price=price
            )
            
            # 发送订单
            result = await self.platform.send_order(order_data)
            
            if not result.get("success"):
                logger.warning(f"❌ 下单失败: {result.get('error')}")
                return None
            
            order_id = result.get("order_id")
            logger.info(f"✅ 订单已提交: {order_id}")
            
            # 启动订单监控 (防狙击)
            asyncio.create_task(
                self._monitor_order(order_id, market.id, side, price, size)
            )
            
            return order_id
            
        except Exception as e:
            logger.error(f"❌ 下单错误: {e}")
            return None
    
    async def _monitor_order(self, order_id: str, market_id: str, side: str, price: Decimal, size: Decimal):
        """
        监控订单状态
        
        防狙击逻辑:
        1. 如果订单在 X 秒内完全成交 -> 可能被狙击，记录
        2. 如果订单部分成交 -> 正常
        3. 如果订单超时未成交 -> 取消重挂
        """
        start_time = datetime.now()
        check_interval = 5  # 每 5 秒检查一次
        
        while (datetime.now() - start_time).seconds < self.order_lifetime:
            await asyncio.sleep(check_interval)
            
            try:
                # 查询订单状态
                order = await self.platform.get_order(order_id)
                
                if not order:
                    logger.warning(f"⚠️ 订单 {order_id} 不存在")
                    break
                
                filled = order.get("filled_size", Decimal("0"))
                remaining = order.get("remaining_size", size)
                
                # 检查是否被狙击 (短时间内完全成交)
                elapsed = (datetime.now() - start_time).seconds
                if filled >= size * Decimal("0.9") and elapsed < 10:
                    logger.warning(f"🎯 订单可能被狙击! {order_id} ({elapsed}s 内成交)")
                    self.stats["sniped_count"] += 1
                    break
                
                # 完全成交
                if remaining <= 0:
                    logger.info(f"✅ 订单完全成交: {order_id}")
                    self.stats["trades"] += 1
                    self.stats["volume"] += size
                    break
                
            except Exception as e:
                logger.error(f"❌ 监控订单错误: {e}")
                break
        
        else:
            # 超时，取消订单
            logger.info(f"⏰ 订单超时，取消: {order_id}")
            try:
                await self.platform.cancel_order(order_id)
                self.stats["cancelled_count"] += 1
            except Exception as e:
                logger.error(f"❌ 取消订单失败: {e}")
    
    async def _check_auto_pause(self) -> bool:
        """
        检查是否需要自动暂停
        
        条件: 被狙击次数 > 阈值 且 交易次数 >= 最小检查数
        """
        if self.stats["trades"] < self.min_trades_for_check:
            return False
        
        snipe_rate = self.stats["sniped_count"] / max(self.stats["trades"], 1)
        
        if self.stats["sniped_count"] >= self.snipe_pause_threshold and snipe_rate > 0.3:
            logger.warning(f"🛑 被狙击频率过高 ({self.stats['sniped_count']}/{self.stats['trades']}), 暂停 {self.snipe_pause_duration}s")
            self.is_paused = True
            self.pause_until = datetime.now() + timedelta(seconds=self.snipe_pause_duration)
            self.stats["paused_count"] += 1
            return True
        
        return False
    
    async def _check_pause_status(self):
        """检查暂停状态，如果暂停时间已过则恢复"""
        if self.is_paused and self.pause_until:
            if datetime.now() >= self.pause_until:
                logger.info("✅ 暂停结束，恢复交易")
                self.is_paused = False
                self.pause_until = None
                # 重置统计，给新机会
                self.stats["sniped_count"] = 0
                self.stats["trades"] = 0
            else:
                remaining = (self.pause_until - datetime.now()).seconds
                logger.info(f"⏸️  策略暂停中，剩余 {remaining}s")
                await asyncio.sleep(min(remaining, 30))
    
    async def _check_cost_efficiency(self, size: Decimal, market) -> bool:
        """
        检查成本效率
        
        预估 Gas 成本，如果过高则跳过
        """
        try:
            # 预估 Gas 成本 (Base 链约 0.001-0.01 USDC)
            estimated_gas = Decimal("0.005")  # 简化估算
            
            # 预估利润 (基于 spread)
            spread = market.yes_price + market.no_price - Decimal("1")
            estimated_profit = size * spread * Decimal("0.5")  # 假设成交一半
            
            # 检查是否值得
            if estimated_gas > self.max_gas_cost_usd:
                logger.warning(f"💸 Gas 成本过高: ${estimated_gas}, 跳过")
                self.stats["skipped_for_cost"] += 1
                return False
            
            if estimated_profit < size * self.min_profit_margin:
                logger.debug(f"📉 利润边际太小: ${estimated_profit}, 跳过")
                return False
            
            self.total_gas_cost += estimated_gas
            self.estimated_profit += estimated_profit
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 成本检查错误: {e}")
            return True  # 出错时默认继续
    
    async def run(self):
        """运行防狙击做市策略"""
        logger.info("🚀 启动防狙击做市策略")
        logger.info(f"   基础金额: {self.base_trade_size} USDC")
        logger.info(f"   随机间隔: {self.min_interval}-{self.max_interval}s")
        logger.info(f"   订单存活: {self.order_lifetime}s")
        logger.info(f"   自动暂停: {self.snipe_pause_threshold}次狙击/{self.min_trades_for_check}笔交易")
        logger.info(f"   成本限制: Gas<${self.max_gas_cost_usd}, 利润>{self.min_profit_margin*100}%")
        
        self.running = True
        
        while self.running:
            try:
                # 1. 检查暂停状态
                if self.is_paused:
                    await self._check_pause_status()
                    if self.is_paused:
                        continue
                
                # 2. 检查是否需要自动暂停
                if await self._check_auto_pause():
                    continue
                
                # 3. 获取市场
                markets = await self.platform.get_all_markets()
                
                # 4. 筛选最优市场 (积分效率最高)
                suitable_markets = [
                    m for m in markets
                    if m.liquidity > 10000           # 足够流动性
                    and m.volume_24h > 5000          # 有交易量
                    and abs(m.yes_price - Decimal("0.5")) < Decimal("0.1")  # 接近50/50
                ]
                
                if not suitable_markets:
                    logger.debug("未找到合适的市场")
                    await asyncio.sleep(self._randomize_interval())
                    continue
                
                # 5. 选择最优市场 (按积分效率排序)
                # 积分效率 = 交易量 / 流动性 (越高越好成交)
                suitable_markets.sort(
                    key=lambda m: m.volume_24h / max(m.liquidity, 1),
                    reverse=True
                )
                
                # 前3个中随机选择 (兼顾效率和随机性)
                market = random.choice(suitable_markets[:3])
                
                logger.info(f"📊 选择市场: {market.question[:50]}...")
                logger.info(f"   流动性: ${market.liquidity:,.0f} | 24h量: ${market.volume_24h:,.0f}")
                logger.info(f"   价格: YES {market.yes_price:.3f} | NO {market.no_price:.3f}")
                
                # 6. 成本效率检查
                if not await self._check_cost_efficiency(self.base_trade_size, market):
                    await asyncio.sleep(self._randomize_interval())
                    continue
                
                # 7. 随机决定单边或双边
                if random.random() > 0.5:
                    # 双边做市
                    await self._place_snipe_resistant_order(market, "yes", market.yes_price)
                    await asyncio.sleep(random.randint(2, 5))  # 短暂间隔
                    await self._place_snipe_resistant_order(market, "no", market.no_price)
                else:
                    # 单边 (随机选择)
                    side = random.choice(["yes", "no"])
                    price = market.yes_price if side == "yes" else market.no_price
                    await self._place_snipe_resistant_order(market, side, price)
                
                # 8. 随机间隔后下次交易
                interval = self._randomize_interval()
                logger.info(f"⏳ 等待 {interval}s 后下次交易...")
                logger.info(f"📊 统计: {self.stats['trades']} 笔, {self.stats['volume']} USDC, 被狙击: {self.stats['sniped_count']}")
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"❌ 策略错误: {e}")
                await asyncio.sleep(self._randomize_interval())
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total_trades = max(self.stats["trades"], 1)
        return {
            **self.stats,
            "snipe_rate": self.stats["sniped_count"] / total_trades,
            "cancel_rate": self.stats["cancelled_count"] / total_trades,
            "pause_rate": self.stats["paused_count"] / total_trades,
            "cost_skip_rate": self.stats["skipped_for_cost"] / total_trades,
            "total_gas_cost": self.total_gas_cost,
            "estimated_profit": self.estimated_profit,
            "net_estimated": self.estimated_profit - self.total_gas_cost,
            "is_paused": self.is_paused,
            "pause_until": self.pause_until.isoformat() if self.pause_until else None
        }
