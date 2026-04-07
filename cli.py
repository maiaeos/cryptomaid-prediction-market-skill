"""
统一 CLI 工具
整合套利、做市、撸毛、监控功能
"""

import asyncio
import argparse
import json
import os
import sys
from decimal import Decimal
from typing import Dict, Optional

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入组件
from arbitrage_engine import ArbitrageEngine
from farming_strategies import FarmingOrchestrator, VolumeFarming, LiquidityMining
from venus_monitor import VenusArbitrageBot
from telegram_notifier import TelegramNotifier


def load_config() -> Dict:
    """加载配置"""
    return {
        # Limitless
        "limitless_api_key": os.getenv("LIMITLESS_API_KEY"),
        "limitless_account": os.getenv("LIMITLESS_ACCOUNT"),
        
        # Polymarket
        "polymarket_private_key": os.getenv("POLYMARKET_PRIVATE_KEY"),
        "polymarket_rpc": os.getenv("POLYMARKET_RPC", "https://polygon-rpc.com"),
        
        # Predict.fun
        "predict_fun_api_key": os.getenv("PREDICT_FUN_API_KEY"),
        "predict_fun_private_key": os.getenv("PREDICT_FUN_PRIVATE_KEY"),
        "predict_fun_rpc": os.getenv("PREDICT_FUN_RPC", "https://bsc-dataseed.binance.org"),
        
        # Telegram
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        
        # OneKey
        "onekey_enabled": os.getenv("ONEKEY_ENABLED", "false").lower() == "true",
        "onekey_bridge_url": os.getenv("ONEKEY_BRIDGE_URL", "http://localhost:21320"),
        
        # 套利参数
        "min_profit_pct": Decimal(os.getenv("MIN_PROFIT_PCT", "0.005")),
        "max_arb_size": Decimal(os.getenv("MAX_ARB_SIZE", "100")),
        "scan_interval": int(os.getenv("SCAN_INTERVAL", "60")),
        
        # Venus
        "venus_enabled": os.getenv("VENUS_ENABLED", "false").lower() == "true",
        "bsc_rpc": os.getenv("BSC_RPC", "https://bsc-dataseed.binance.org"),
        "venus_private_key": os.getenv("VENUS_PRIVATE_KEY"),
    }


async def cmd_arbitrage_scan(args):
    """套利扫描命令"""
    print("🔍 启动套利扫描...")
    
    config = load_config()
    engine = ArbitrageEngine(config)
    
    opportunities = await engine.run_scan()
    
    if opportunities:
        print(f"\n✅ 发现 {len(opportunities)} 个套利机会")
        for i, opp in enumerate(opportunities[:5], 1):
            print(f"\n{i}. {opp['question'][:60]}...")
            print(f"   利润: {float(opp['profit_pct'])*100:.2f}%")
            print(f"   策略: {opp['platform_a']} YES + {opp['platform_b']} NO")
    else:
        print("\n❌ 未发现套利机会")


async def cmd_arbitrage_monitor(args):
    """套利监控命令"""
    print("🔄 启动套利监控...")
    print("按 Ctrl+C 停止\n")
    
    config = load_config()
    engine = ArbitrageEngine(config)
    
    await engine.run_monitor(interval=args.interval)


async def cmd_farming_volume(args):
    """刷量策略命令"""
    print("💰 启动交易量刷分策略...")
    
    config = load_config()
    
    # 创建平台连接
    from platforms import LimitlessPlatform
    
    platform = LimitlessPlatform(config["limitless_api_key"])
    
    strategy_config = {
        "trade_size": Decimal(args.size),
        "interval": args.interval,
    }
    
    strategy = VolumeFarming(platform, strategy_config)
    
    try:
        await strategy.run()
    except KeyboardInterrupt:
        print("\n👋 停止策略")
        strategy.stop()


async def cmd_farming_liquidity(args):
    """流动性挖矿命令"""
    print("💧 启动流动性挖矿策略...")
    
    config = load_config()
    
    from platforms import LimitlessPlatform
    
    platform = LimitlessPlatform(config["limitless_api_key"])
    
    strategy_config = {
        "quote_size": Decimal(args.size),
        "spread": Decimal(args.spread),
    }
    
    strategy = LiquidityMining(platform, strategy_config)
    
    try:
        await strategy.run()
    except KeyboardInterrupt:
        print("\n👋 停止策略")
        strategy.stop()


async def cmd_venus_monitor(args):
    """Venus 清算监控命令"""
    print("🚨 启动 Venus 清算监控...")
    
    config = load_config()
    
    bot_config = {
        "bsc_rpc": config["bsc_rpc"],
        "private_key": config["venus_private_key"],
        "check_interval": args.interval,
    }
    
    bot = VenusArbitrageBot(bot_config)
    
    # 添加监控账户
    if args.accounts:
        for addr in args.accounts:
            bot.monitor.add_watched_account(addr)
    
    if args.accounts_file:
        bot.monitor.add_watched_accounts_from_file(args.accounts_file)
    
    await bot.run()


async def cmd_status(args):
    """状态查询命令"""
    print("📊 系统状态\n")
    
    config = load_config()
    
    # 检查配置
    print("配置状态:")
    print(f"  Limitless API: {'✅' if config['limitless_api_key'] else '❌'}")
    print(f"  Polymarket: {'✅' if config['polymarket_private_key'] else '❌'}")
    print(f"  Predict.fun: {'✅' if config['predict_fun_api_key'] else '❌'}")
    print(f"  Telegram: {'✅' if config['telegram_bot_token'] else '❌'}")
    print(f"  OneKey: {'✅' if config['onekey_enabled'] else '❌'}")
    print(f"  Venus: {'✅' if config['venus_enabled'] else '❌'}")


async def cmd_test_telegram(args):
    """测试 Telegram 通知"""
    print("📤 测试 Telegram 通知...")
    
    config = load_config()
    
    if not config["telegram_bot_token"]:
        print("❌ 未配置 Telegram Bot Token")
        return
    
    notifier = TelegramNotifier(
        bot_token=config["telegram_bot_token"],
        chat_id=config["telegram_chat_id"]
    )
    
    success = await notifier.send_message(
        "🧪 *测试消息*\n\n套利系统测试通知正常工作！"
    )
    
    if success:
        print("✅ Telegram 测试成功")
    else:
        print("❌ Telegram 测试失败")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="预测市场套利与做市系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 扫描套利机会
  python cli.py arbitrage scan
  
  # 持续监控套利
  python cli.py arbitrage monitor --interval 30
  
  # 启动刷量策略
  python cli.py farming volume --size 10 --interval 60
  
  # 启动流动性挖矿
  python cli.py farming liquidity --size 100 --spread 0.01
  
  # Venus 清算监控
  python cli.py venus monitor --accounts 0x... 0x...
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 套利命令
    arb_parser = subparsers.add_parser("arbitrage", help="套利相关命令")
    arb_subparsers = arb_parser.add_subparsers(dest="arb_cmd")
    
    arb_scan = arb_subparsers.add_parser("scan", help="扫描套利机会")
    arb_scan.set_defaults(func=cmd_arbitrage_scan)
    
    arb_monitor = arb_subparsers.add_parser("monitor", help="持续监控套利")
    arb_monitor.add_argument("--interval", type=int, default=60, help="扫描间隔(秒)")
    arb_monitor.set_defaults(func=cmd_arbitrage_monitor)
    
    # 撸毛命令
    farm_parser = subparsers.add_parser("farming", help="撸毛策略")
    farm_subparsers = farm_parser.add_subparsers(dest="farm_cmd")
    
    farm_vol = farm_subparsers.add_parser("volume", help="刷量策略")
    farm_vol.add_argument("--size", type=str, default="10", help="单笔金额")
    farm_vol.add_argument("--interval", type=int, default=60, help="交易间隔")
    farm_vol.set_defaults(func=cmd_farming_volume)
    
    farm_liq = farm_subparsers.add_parser("liquidity", help="流动性挖矿")
    farm_liq.add_argument("--size", type=str, default="100", help="挂单金额")
    farm_liq.add_argument("--spread", type=str, default="0.01", help="目标 spread")
    farm_liq.set_defaults(func=cmd_farming_liquidity)
    
    # Venus 命令
    venus_parser = subparsers.add_parser("venus", help="Venus 清算监控")
    venus_subparsers = venus_parser.add_subparsers(dest="venus_cmd")
    
    venus_monitor = venus_subparsers.add_parser("monitor", help="监控清算机会")
    venus_monitor.add_argument("--accounts", nargs="+", help="监控的账户地址")
    venus_monitor.add_argument("--accounts-file", help="账户地址文件")
    venus_monitor.add_argument("--interval", type=int, default=30, help="检查间隔")
    venus_monitor.set_defaults(func=cmd_venus_monitor)
    
    # 状态命令
    status_parser = subparsers.add_parser("status", help="查看系统状态")
    status_parser.set_defaults(func=cmd_status)
    
    # 测试命令
    test_parser = subparsers.add_parser("test", help="测试功能")
    test_parser.add_argument("--telegram", action="store_true", help="测试 Telegram")
    test_parser.set_defaults(func=cmd_test_telegram)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 执行命令
    if hasattr(args, 'func'):
        asyncio.run(args.func(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
