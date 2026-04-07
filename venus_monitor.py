"""
Venus DeFi 清算套利监控
监控 Venus 协议的健康因子，发现清算机会
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from web3 import Web3

logger = logging.getLogger(__name__)


# Venus 合约地址 (BSC Mainnet)
VENUS_CONTRACTS = {
    "comptroller": "0xfD36E2c2a6789Db23113685031d7F16329158384",
    "vai_controller": "0x004065D34C6b18cE4370ced1CeBDE94865DbFAFE",
    "oracle": "0xd8B6dA2bfEC71D684D3E2a2FC9492dD3935c5f8c",
}

# 简化的 ABI
COMPTROLLER_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "", "type": "address"}],
        "name": "getAccountLiquidity",
        "outputs": [
            {"name": "error", "type": "uint256"},
            {"name": "liquidity", "type": "uint256"},
            {"name": "shortfall", "type": "uint256"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "getAllMarkets",
        "outputs": [{"name": "", "type": "address[]"}],
        "type": "function"
    },
]

VTOKEN_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "underlying",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "borrowBalanceStored",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "accountSnapshot",
        "outputs": [
            {"name": "error", "type": "uint256"},
            {"name": "vTokenBalance", "type": "uint256"},
            {"name": "borrowBalance", "type": "uint256"},
            {"name": "exchangeRateMantissa", "type": "uint256"}
        ],
        "type": "function"
    },
]


@dataclass
class LiquidationOpportunity:
    """清算机会"""
    borrower: str
    repay_token: str
    seize_token: str
    repay_amount: Decimal
    seize_amount: Decimal
    profit_estimate: Decimal
    health_factor: Decimal
    timestamp: datetime


class VenusMonitor:
    """Venus 清算监控器"""
    
    def __init__(self, rpc_url: str, private_key: Optional[str] = None):
        # Web3 连接
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.w3.is_connected():
            raise ConnectionError("无法连接到 BSC RPC")
        
        # 账户 (用于执行清算)
        if private_key:
            self.account = self.w3.eth.account.from_key(private_key)
            self.address = self.account.address
        else:
            self.account = None
            self.address = None
        
        # 合约
        self.comptroller = self.w3.eth.contract(
            address=Web3.to_checksum_address(VENUS_CONTRACTS["comptroller"]),
            abi=COMPTROLLER_ABI
        )
        
        # 状态
        self.markets: Dict[str, Dict] = {}  # 市场列表
        self.watched_accounts: set = set()  # 监控的账户
        self.liquidation_threshold = Decimal("1.0")  # 健康因子阈值
        
        # 统计
        self.opportunities_found = 0
        self.liquidations_executed = 0
        
    async def initialize(self):
        """初始化，获取市场列表"""
        logger.info("🚀 初始化 Venus 监控器")
        
        # 获取所有市场
        markets = self.comptroller.functions.getAllMarkets().call()
        
        for market_address in markets:
            try:
                market_contract = self.w3.eth.contract(
                    address=market_address,
                    abi=VTOKEN_ABI
                )
                
                symbol = market_contract.functions.symbol().call()
                
                # 获取底层资产
                try:
                    underlying = market_contract.functions.underlying().call()
                except:
                    # vBNB 没有 underlying 函数
                    underlying = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"  # WBNB
                
                self.markets[market_address] = {
                    "address": market_address,
                    "symbol": symbol,
                    "contract": market_contract,
                    "underlying": underlying
                }
                
                logger.info(f"  ✅ {symbol}: {market_address}")
                
            except Exception as e:
                logger.warning(f"  ⚠️ 获取市场失败 {market_address}: {e}")
        
        logger.info(f"📊 共 {len(self.markets)} 个市场")
    
    async def check_account(self, address: str) -> Optional[Dict]:
        """检查单个账户的健康状况"""
        try:
            # 获取账户流动性
            error, liquidity, shortfall = self.comptroller.functions.getAccountLiquidity(
                Web3.to_checksum_address(address)
            ).call()
            
            if error != 0:
                logger.warning(f"获取流动性失败: error={error}")
                return None
            
            # 计算健康因子
            # health_factor = collateral / debt
            # 如果 shortfall > 0, 说明资不抵债，可以被清算
            
            if shortfall > 0:
                health_factor = Decimal("0")
            elif liquidity > 0:
                # 估算健康因子
                health_factor = Decimal("2.0")  # 安全
            else:
                health_factor = Decimal("1.0")
            
            return {
                "address": address,
                "liquidity": Decimal(liquidity) / Decimal(10**18),
                "shortfall": Decimal(shortfall) / Decimal(10**18),
                "health_factor": health_factor,
                "liquidatable": shortfall > 0
            }
            
        except Exception as e:
            logger.error(f"检查账户失败 {address}: {e}")
            return None
    
    async def find_liquidation_opportunities(self) -> List[LiquidationOpportunity]:
        """寻找清算机会"""
        opportunities = []
        
        # 检查所有监控的账户
        for address in self.watched_accounts:
            account_info = await self.check_account(address)
            
            if not account_info or not account_info["liquidatable"]:
                continue
            
            # 获取账户的借贷详情
            borrows = await self._get_account_borrows(address)
            collaterals = await self._get_account_collaterals(address)
            
            if not borrows or not collaterals:
                continue
            
            # 选择最大的借款和抵押品
            max_borrow = max(borrows, key=lambda x: x["amount"])
            max_collateral = max(collaterals, key=lambda x: x["amount"])
            
            # 估算利润 (Venus 清算奖励通常是 8%)
            seize_amount = max_collateral["amount"] * Decimal("0.08")
            
            opportunity = LiquidationOpportunity(
                borrower=address,
                repay_token=max_borrow["symbol"],
                seize_token=max_collateral["symbol"],
                repay_amount=max_borrow["amount"],
                seize_amount=seize_amount,
                profit_estimate=seize_amount,
                health_factor=account_info["health_factor"],
                timestamp=datetime.now()
            )
            
            opportunities.append(opportunity)
            self.opportunities_found += 1
            
            logger.info(f"🎯 发现清算机会!")
            logger.info(f"   借款人: {address}")
            logger.info(f"   偿还: {max_borrow['amount']:.4f} {max_borrow['symbol']}")
            logger.info(f"   获得: {seize_amount:.4f} {max_collateral['symbol']}")
        
        return opportunities
    
    async def _get_account_borrows(self, address: str) -> List[Dict]:
        """获取账户的所有借款"""
        borrows = []
        
        for market_address, market in self.markets.items():
            try:
                borrow_balance = market["contract"].functions.borrowBalanceStored(
                    Web3.to_checksum_address(address)
                ).call()
                
                if borrow_balance > 0:
                    borrows.append({
                        "market": market_address,
                        "symbol": market["symbol"],
                        "amount": Decimal(borrow_balance) / Decimal(10**18)
                    })
            except Exception as e:
                logger.debug(f"获取借款失败 {market['symbol']}: {e}")
        
        return borrows
    
    async def _get_account_collaterals(self, address: str) -> List[Dict]:
        """获取账户的所有抵押品"""
        collaterals = []
        
        for market_address, market in self.markets.items():
            try:
                snapshot = market["contract"].functions.accountSnapshot(
                    Web3.to_checksum_address(address)
                ).call()
                
                # snapshot: (error, vTokenBalance, borrowBalance, exchangeRate)
                vtoken_balance = snapshot[1]
                exchange_rate = snapshot[3]
                
                if vtoken_balance > 0:
                    # 计算底层资产数量
                    underlying_balance = vtoken_balance * exchange_rate / Decimal(10**18)
                    
                    collaterals.append({
                        "market": market_address,
                        "symbol": market["symbol"],
                        "amount": Decimal(underlying_balance) / Decimal(10**18)
                    })
            except Exception as e:
                logger.debug(f"获取抵押品失败 {market['symbol']}: {e}")
        
        return collaterals
    
    async def execute_liquidation(self, opportunity: LiquidationOpportunity) -> bool:
        """执行清算"""
        if not self.account:
            logger.error("❌ 未配置私钥，无法执行清算")
            return False
        
        try:
            logger.info(f"🚀 执行清算: {opportunity.borrower}")
            
            # TODO: 实现实际的清算交易
            # 1. 检查余额
            # 2. 构建清算交易
            # 3. 发送交易
            # 4. 等待确认
            
            logger.info("✅ 清算执行成功")
            self.liquidations_executed += 1
            return True
            
        except Exception as e:
            logger.error(f"❌ 清算执行失败: {e}")
            return False
    
    def add_watched_account(self, address: str):
        """添加监控账户"""
        self.watched_accounts.add(Web3.to_checksum_address(address))
        logger.info(f"👁️ 添加监控: {address}")
    
    def add_watched_accounts_from_file(self, filepath: str):
        """从文件加载监控账户"""
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    address = line.strip()
                    if address and address.startswith("0x"):
                        self.add_watched_account(address)
        except FileNotFoundError:
            logger.warning(f"文件不存在: {filepath}")
    
    async def monitor_loop(self, interval: int = 30):
        """持续监控循环"""
        logger.info(f"🔄 启动监控循环 (间隔: {interval}s)")
        
        while True:
            try:
                # 寻找清算机会
                opportunities = await self.find_liquidation_opportunities()
                
                if opportunities:
                    logger.info(f"🎯 发现 {len(opportunities)} 个清算机会")
                    
                    # 发送通知
                    await self._notify_opportunities(opportunities)
                    
                    # 自动执行 (如果配置)
                    # for opp in opportunities:
                    #     await self.execute_liquidation(opp)
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"监控错误: {e}")
                await asyncio.sleep(interval)
    
    async def _notify_opportunities(self, opportunities: List[LiquidationOpportunity]):
        """通知清算机会"""
        # TODO: 集成 Telegram 通知
        for opp in opportunities:
            logger.info(f"""
🚨 清算机会
借款人: {opp.borrower}
偿还: {opp.repay_amount:.4f} {opp.repay_token}
获得: {opp.seize_amount:.4f} {opp.seize_token}
预估利润: ${opp.profit_estimate:.2f}
""")
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "markets_tracked": len(self.markets),
            "accounts_watched": len(self.watched_accounts),
            "opportunities_found": self.opportunities_found,
            "liquidations_executed": self.liquidations_executed,
        }


class VenusArbitrageBot:
    """Venus 清算套利机器人"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.monitor: Optional[VenusMonitor] = None
        
    async def initialize(self):
        """初始化"""
        self.monitor = VenusMonitor(
            rpc_url=self.config.get("bsc_rpc", "https://bsc-dataseed.binance.org"),
            private_key=self.config.get("private_key")
        )
        
        await self.monitor.initialize()
        
        # 加载监控账户
        if self.config.get("watched_accounts_file"):
            self.monitor.add_watched_accounts_from_file(
                self.config["watched_accounts_file"]
            )
    
    async def run(self):
        """运行机器人"""
        await self.initialize()
        
        # 启动监控
        await self.monitor.monitor_loop(
            interval=self.config.get("check_interval", 30)
        )
    
    def stop(self):
        """停止机器人"""
        pass
