"""
预测市场套利引擎核心
支持 Limitless + Polymarket + Predict.fun 三平台套利
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from platforms.base import PredictionMarket
from platforms.limitless import LimitlessPlatform
from platforms.polymarket import PolymarketPlatform
from platforms.predict_fun import PredictFunPlatform
from wallet_manager import OneKeyManager
from telegram_notifier import TelegramNotifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MarketPrice:
    """统一的市场价格数据结构"""
    platform: str
    market_id: str
    market_slug: str
    question: str
    yes_price: Decimal
    no_price: Decimal
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    volume_24h: Decimal = Decimal("0")
    liquidity: Decimal = Decimal("0")
    expires_at: Optional[datetime] = None
    raw_data: Dict = field(default_factory=dict)
    
    @property
    def spread(self) -> Decimal:
        """买卖价差"""
        return self.yes_price + self.no_price - Decimal("1")
    
    @property
    def mid_price(self) -> Decimal:
        """中间价"""
        return (self.yes_price + (Decimal("1") - self.no_price)) / Decimal("2")


@dataclass
class ArbitrageOpportunity:
    """套利机会数据结构"""
    # 市场信息
    question: str
    market_slug_a: str
    market_slug_b: str
    
    # 平台 A (买 YES)
    platform_a: str
    yes_price_a: Decimal
    yes_token_id_a: Optional[str]
    
    # 平台 B (买 NO)
    platform_b: str
    no_price_b: Decimal
    no_token_id_b: Optional[str]
    
    # 套利计算
    total_cost: Decimal
    profit: Decimal
    profit_pct: Decimal
    fees: Decimal
    
    # 元数据
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_profitable(self) -> bool:
        """是否有利润"""
        return self.profit > Decimal("0.001")  # 至少 0.1% 利润
    
    def to_dict(self) -> Dict:
        return {
            "question": self.question,
            "platform_a": self.platform_a,
            "platform_b": self.platform_b,
            "yes_price_a": float(self.yes_price_a),
            "no_price_b": float(self.no_price_b),
            "total_cost": float(self.total_cost),
            "profit": float(self.profit),
            "profit_pct": float(self.profit_pct),
            "timestamp": self.timestamp.isoformat(),
        }


class ArbitrageEngine:
    """套利引擎主类"""
    
    # 平台手续费配置 (taker fee)
    PLATFORM_FEES = {
        "limitless": Decimal("0.0075"),    # 0.75%
        "polymarket": Decimal("0.02"),     # 2%
        "predict_fun": Decimal("0.02"),    # 2% (estimated)
    }
    
    def __init__(self, config: Dict):
        self.config = config
        self.platforms: Dict[str, PredictionMarket] = {}
        self.onekey: Optional[OneKeyManager] = None
        self.telegram: Optional[TelegramNotifier] = None
        
        # 初始化平台
        self._init_platforms()
        
        # 初始化通知
        if config.get("telegram_bot_token"):
            self.telegram = TelegramNotifier(
                bot_token=config["telegram_bot_token"],
                chat_id=config["telegram_chat_id"]
            )
        
        # 初始化 OneKey
        if config.get("onekey_enabled"):
            self.onekey = OneKeyManager(bridge_url=config.get("onekey_bridge_url"))
    
    def _init_platforms(self):
        """初始化各平台连接"""
        # Limitless (已有 API Key)
        if self.config.get("limitless_api_key"):
            self.platforms["limitless"] = LimitlessPlatform(
                api_key=self.config["limitless_api_key"]
            )
            logger.info("✅ Limitless 平台已初始化")
        
        # Polymarket (合约交互)
        if self.config.get("polymarket_private_key"):
            self.platforms["polymarket"] = PolymarketPlatform(
                rpc_url=self.config.get("polymarket_rpc", "https://polygon-rpc.com"),
                private_key=self.config["polymarket_private_key"]
            )
            logger.info("✅ Polymarket 平台已初始化")
        
        # Predict.fun (等 API Key)
        if self.config.get("predict_fun_api_key"):
            self.platforms["predict_fun"] = PredictFunPlatform(
                api_key=self.config["predict_fun_api_key"],
                rpc_url=self.config.get("predict_fun_rpc", "https://bsc-dataseed.binance.org")
            )
            logger.info("✅ Predict.fun 平台已初始化")
    
    async def scan_all_markets(self) -> Dict[str, List[MarketPrice]]:
        """扫描所有平台的活跃市场"""
        all_prices = {}
        
        for name, platform in self.platforms.items():
            try:
                logger.info(f"🔍 扫描 {name} 市场...")
                prices = await platform.get_all_prices()
                all_prices[name] = prices
                logger.info(f"   找到 {len(prices)} 个市场")
            except Exception as e:
                logger.error(f"❌ {name} 扫描失败: {e}")
                all_prices[name] = []
        
        return all_prices
    
    def find_arbitrage_opportunities(
        self, 
        all_prices: Dict[str, List[MarketPrice]],
        min_profit_pct: Decimal = Decimal("0.005")  # 最小 0.5% 利润
    ) -> List[ArbitrageOpportunity]:
        """
        发现套利机会
        
        策略: 在平台 A 买 YES + 在平台 B 买 NO
        条件: YES_price_A + NO_price_B < 1.00 - fees
        """
        opportunities = []
        
        platform_names = list(all_prices.keys())
        
        # 两两比较平台
        for i, platform_a in enumerate(platform_names):
            for platform_b in platform_names[i+1:]:
                
                prices_a = all_prices[platform_a]
                prices_b = all_prices[platform_b]
                
                # 寻找匹配的市场
                for price_a in prices_a:
                    for price_b in prices_b:
                        # 检查是否是同一市场 (基于标题相似度)
                        if not self._is_same_market(price_a, price_b):
                            continue
                        
                        # 计算两种套利方向
                        # 方向 1: A买YES + B买NO
                        opp1 = self._calculate_arbitrage(
                            price_a, price_b, 
                            platform_a, platform_b
                        )
                        if opp1 and opp1.profit_pct >= min_profit_pct:
                            opportunities.append(opp1)
                        
                        # 方向 2: B买YES + A买NO
                        opp2 = self._calculate_arbitrage(
                            price_b, price_a,
                            platform_b, platform_a
                        )
                        if opp2 and opp2.profit_pct >= min_profit_pct:
                            opportunities.append(opp2)
        
        # 按利润排序
        opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        return opportunities
    
    def _is_same_market(self, price_a: MarketPrice, price_b: MarketPrice) -> bool:
        """判断两个价格是否来自同一市场"""
        # TODO: 实现更智能的匹配算法
        # 目前简单比较关键词
        import re
        
        def normalize(text: str) -> set:
            text = text.lower()
            text = re.sub(r'[^\w\s]', ' ', text)
            return set(text.split())
        
        words_a = normalize(price_a.question)
        words_b = normalize(price_b.question)
        
        # 计算重叠度
        if not words_a or not words_b:
            return False
        
        overlap = len(words_a & words_b)
        similarity = overlap / max(len(words_a), len(words_b))
        
        return similarity > 0.6  # 60% 相似度阈值
    
    def _calculate_arbitrage(
        self,
        yes_market: MarketPrice,
        no_market: MarketPrice,
        yes_platform: str,
        no_platform: str
    ) -> Optional[ArbitrageOpportunity]:
        """计算套利机会"""
        
        yes_price = yes_market.yes_price
        no_price = no_market.no_price
        
        # 计算成本
        total_cost = yes_price + no_price
        
        # 计算手续费
        yes_fee = yes_price * self.PLATFORM_FEES.get(yes_platform, Decimal("0.02"))
        no_fee = no_price * self.PLATFORM_FEES.get(no_platform, Decimal("0.02"))
        total_fees = yes_fee + no_fee
        
        # 计算净利润
        profit = Decimal("1") - total_cost - total_fees
        profit_pct = profit / total_cost if total_cost > 0 else Decimal("0")
        
        return ArbitrageOpportunity(
            question=yes_market.question,
            market_slug_a=yes_market.market_slug,
            market_slug_b=no_market.market_slug,
            platform_a=yes_platform,
            yes_price_a=yes_price,
            yes_token_id_a=yes_market.yes_token_id,
            platform_b=no_platform,
            no_price_b=no_price,
            no_token_id_b=no_market.no_token_id,
            total_cost=total_cost,
            profit=profit,
            profit_pct=profit_pct,
            fees=total_fees
        )
    
    async def notify_opportunity(self, opp: ArbitrageOpportunity):
        """通知套利机会"""
        if not self.telegram:
            logger.warning("⚠️ Telegram 未配置，无法推送")
            return
        
        message = f"""
🎯 **套利机会发现！**

**市场**: {opp.question[:80]}...

**策略**:
• {opp.platform_a}: 买 YES @ ${float(opp.yes_price_a):.4f}
• {opp.platform_b}: 买 NO @ ${float(opp.no_price_b):.4f}

**利润**: ${float(opp.profit):.4f} ({float(opp.profit_pct)*100:.2f}%)
**手续费**: ${float(opp.fees):.4f}
**总成本**: ${float(opp.total_cost):.4f}

⏰ {opp.timestamp.strftime('%H:%M:%S')}

点击确认执行套利
"""
        await self.telegram.send_message(message)
    
    async def execute_arbitrage(self, opp: ArbitrageOpportunity, size: Decimal):
        """
        执行套利交易
        
        流程:
        1. 检查 OneKey 连接
        2. 构建交易
        3. 请求签名
        4. 发送交易
        """
        if not self.onekey:
            logger.error("❌ OneKey 未配置")
            return False
        
        logger.info(f"🚀 开始执行套利: {opp.question[:50]}...")
        
        try:
            # 获取平台实例
            platform_a = self.platforms.get(opp.platform_a)
            platform_b = self.platforms.get(opp.platform_b)
            
            if not platform_a or not platform_b:
                logger.error("❌ 平台未初始化")
                return False
            
            # 构建交易
            tx_a = await platform_a.build_buy_order(
                market_id=opp.yes_token_id_a or opp.market_slug_a,
                side="yes",
                size=size,
                price=opp.yes_price_a
            )
            
            tx_b = await platform_b.build_buy_order(
                market_id=opp.no_token_id_b or opp.market_slug_b,
                side="no",
                size=size,
                price=opp.no_price_b
            )
            
            # OneKey 签名
            logger.info("🔐 等待 OneKey 签名...")
            signed_tx_a = await self.onekey.sign_transaction(tx_a)
            signed_tx_b = await self.onekey.sign_transaction(tx_b)
            
            # 发送交易
            logger.info("📤 发送交易...")
            result_a = await platform_a.send_order(signed_tx_a)
            result_b = await platform_b.send_order(signed_tx_b)
            
            logger.info(f"✅ 套利执行完成!")
            logger.info(f"   {opp.platform_a}: {result_a}")
            logger.info(f"   {opp.platform_b}: {result_b}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 套利执行失败: {e}")
            return False
    
    async def run_scan(self):
        """运行一次扫描"""
        logger.info("=" * 60)
        logger.info("🔍 开始套利扫描")
        logger.info("=" * 60)
        
        # 1. 扫描所有市场
        all_prices = await self.scan_all_markets()
        
        # 2. 发现套利机会
        opportunities = self.find_arbitrage_opportunities(all_prices)
        
        # 3. 通知和执行
        if opportunities:
            logger.info(f"\n🎯 发现 {len(opportunities)} 个套利机会:")
            for i, opp in enumerate(opportunities[:5], 1):
                logger.info(f"\n{i}. {opp.question[:60]}...")
                logger.info(f"   利润: {float(opp.profit_pct)*100:.2f}%")
                logger.info(f"   策略: {opp.platform_a} YES + {opp.platform_b} NO")
                
                # 推送通知
                await self.notify_opportunity(opp)
        else:
            logger.info("\n❌ 未发现套利机会")
        
        return opportunities
    
    async def run_monitor(self, interval: int = 60):
        """持续监控模式"""
        logger.info("=" * 60)
        logger.info(f"🔄 启动监控模式 (间隔: {interval}s)")
        logger.info("=" * 60)
        
        while True:
            try:
                await self.run_scan()
                logger.info(f"\n⏳ 等待 {interval} 秒后下次扫描...")
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                logger.info("\n👋 监控已停止")
                break
            except Exception as e:
                logger.error(f"❌ 监控错误: {e}")
                await asyncio.sleep(interval)


# CLI 入口
if __name__ == "__main__":
    import argparse
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="预测市场套利引擎")
    parser.add_argument("--scan", action="store_true", help="运行一次扫描")
    parser.add_argument("--monitor", action="store_true", help="持续监控")
    parser.add_argument("--interval", type=int, default=60, help="监控间隔(秒)")
    args = parser.parse_args()
    
    # 加载配置
    config = {
        "limitless_api_key": os.getenv("LIMITLESS_API_KEY"),
        "polymarket_private_key": os.getenv("POLYMARKET_PRIVATE_KEY"),
        "polymarket_rpc": os.getenv("POLYMARKET_RPC", "https://polygon-rpc.com"),
        "predict_fun_api_key": os.getenv("PREDICT_FUN_API_KEY"),
        "predict_fun_rpc": os.getenv("PREDICT_FUN_RPC", "https://bsc-dataseed.binance.org"),
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "onekey_enabled": os.getenv("ONEKEY_ENABLED", "false").lower() == "true",
        "onekey_bridge_url": os.getenv("ONEKEY_BRIDGE_URL", "http://localhost:21320"),
    }
    
    # 创建引擎
    engine = ArbitrageEngine(config)
    
    # 运行
    if args.monitor:
        asyncio.run(engine.run_monitor(args.interval))
    elif args.scan:
        asyncio.run(engine.run_scan())
    else:
        parser.print_help()
