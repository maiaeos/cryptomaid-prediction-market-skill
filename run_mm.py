"""
简单启动器 - 无需 OneKey 即可撸毛
"""

import asyncio
import os
from decimal import Decimal
from dotenv import load_dotenv

# 加载配置
env_path = '/Users/animaia/.openclaw/workspace/skills/prediction-arbitrage/.env'
load_dotenv(env_path)

from platforms.limitless_full import LimitlessPlatform
from wallet_providers import PrivateKeyWallet
from anti_snipe_mm import AntiSnipeMarketMaker


async def main():
    print("=" * 70)
    print("🚀 Limitless 防狙击做市机器人")
    print("=" * 70)
    
    # 配置检查
    api_key = os.getenv('LIMITLESS_API_KEY')
    private_key = os.getenv('PRIVATE_KEY')
    
    if not api_key:
        print("❌ 错误: LIMITLESS_API_KEY 未设置")
        print("   请编辑 .env 文件添加")
        return
    
    if not private_key:
        print("⚠️  警告: PRIVATE_KEY 未设置")
        print("   将使用只读模式 (无法交易)")
        print()
        wallet = None
    else:
        # 创建私钥钱包
        print("🔐 初始化私钥钱包...")
        wallet = PrivateKeyWallet(
            private_key=private_key,
            rpc_url="https://mainnet.base.org"
        )
        print(f"✅ 钱包地址: {wallet.address}")
        print()
    
    # 创建 Limitless 平台
    print("📡 连接 Limitless...")
    platform = LimitlessPlatform(
        api_key=api_key,
        wallet_address=wallet.address if wallet else "0x...",
        wallet=wallet
    )
    
    # 测试连接
    try:
        markets = await platform.get_all_markets()
        print(f"✅ 连接成功! 获取到 {len(markets)} 个市场")
        print()
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    # 显示余额
    try:
        balance = await platform.get_balance()
        print(f"💰 账户余额:")
        print(f"   USDC: {balance['USDC']}")
        print(f"   积分: {balance['points']}")
        print()
    except Exception as e:
        print(f"⚠️  获取余额失败: {e}")
        print()
    
    if not wallet:
        print("=" * 70)
        print("📖 只读模式 - 查看市场信息")
        print("=" * 70)
        
        # 显示热门市场
        markets.sort(key=lambda m: m.liquidity, reverse=True)
        print("\n🔥 热门市场:")
        for i, m in enumerate(markets[:5], 1):
            print(f"{i}. {m.question[:50]}...")
            print(f"   YES: ${m.yes_price} | NO: ${m.no_price}")
            print(f"   流动性: ${m.liquidity:,.0f}")
        
        print("\n💡 要启用交易，请设置 PRIVATE_KEY")
        return
    
    # 启动做市策略
    print("=" * 70)
    print("🤖 启动防狙击做市策略")
    print("=" * 70)
    print()
    print("⚙️  配置:")
    print("   基础金额: 10 USDC")
    print("   随机间隔: 30-120 秒")
    print("   订单存活: 60 秒")
    print("   防狙击: 启用")
    print()
    print("⚠️  按 Ctrl+C 停止")
    print("=" * 70)
    print()
    
    # 配置策略
    config = {
        "base_trade_size": 10,
        "max_trade_size": 30,
        "min_interval": 30,
        "max_interval": 120,
        "order_lifetime": 60,
        "price_variance": 0.005,
        "size_variance": 0.2
    }
    
    strategy = AntiSnipeMarketMaker(platform, config)
    
    try:
        await strategy.run()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("⏹️  策略已停止")
        print("=" * 70)
        stats = strategy.get_stats()
        print(f"\n📊 最终统计:")
        print(f"   交易次数: {stats['trades']}")
        print(f"   总交易量: {stats['volume']} USDC")
        print(f"   被狙击次数: {stats['sniped_count']}")
        print(f"   取消订单: {stats['cancelled_count']}")


if __name__ == "__main__":
    asyncio.run(main())
