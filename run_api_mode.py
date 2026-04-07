#!/usr/bin/env python3
"""
Limitless 自动赚积分 - API 模式 (无需私钥)
通过 Limitless API 直接交易
"""
import asyncio
import os
from decimal import Decimal
from dotenv import load_dotenv

env_path = '/Users/animaia/.openclaw/workspace/skills/prediction-arbitrage/.env'
load_dotenv(env_path)

from platforms.limitless_full import LimitlessPlatform
from anti_snipe_mm import AntiSnipeMarketMaker


async def main():
    print("=" * 70)
    print("🚀 Limitless 自动赚积分机器人")
    print("=" * 70)
    print()
    
    # 检查 API Key
    api_key = os.getenv('LIMITLESS_API_KEY')
    wallet_address = os.getenv('LIMITLESS_ACCOUNT_ADDRESS')
    
    if not api_key:
        print("❌ 错误: LIMITLESS_API_KEY 未设置")
        print("   请编辑 .env 文件添加")
        return
    
    if not wallet_address:
        print("❌ 错误: LIMITLESS_ACCOUNT_ADDRESS 未设置")
        print("   请编辑 .env 文件添加你的钱包地址")
        return
    
    print(f"🔑 API Key: {api_key[:20]}...")
    print(f"📍 钱包地址: {wallet_address}")
    print()
    
    # 创建平台连接 (API 模式，无需私钥)
    print("📡 连接 Limitless API...")
    platform = LimitlessPlatform(
        api_key=api_key,
        wallet_address=wallet_address
    )
    
    # 测试连接
    try:
        markets = await platform.get_all_markets()
        print(f"✅ 连接成功! 获取到 {len(markets)} 个市场")
        print()
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return
    
    # 显示余额 (可能失败)
    try:
        balance = await platform.get_balance()
        print(f"💰 账户余额:")
        print(f"   USDC: {balance['USDC']}")
        print(f"   积分: {balance['points']}")
        print()
        
        if balance['USDC'] < 10:
            print("⚠️  USDC 余额不足，请充值")
            return
    except Exception as e:
        print(f"⚠️  获取余额失败 (API限制): {e}")
        print("   继续运行...")
        print()
    
    # 显示最优市场
    print("🔥 积分效率最高的市场:")
    markets.sort(key=lambda m: m.volume_24h / max(m.liquidity, 1), reverse=True)
    for i, m in enumerate(markets[:3], 1):
        efficiency = float(m.volume_24h) / float(m.liquidity) if m.liquidity > 0 else 0
        print(f"{i}. {m.question[:40]}...")
        print(f"   流动性: ${float(m.liquidity):,.0f} | 24h量: ${float(m.volume_24h):,.0f}")
        print(f"   积分效率: {efficiency:.2f}")
    print()
    
    # 启动策略
    print("=" * 70)
    print("🤖 启动高胜率刷量策略 (S3赛季优化版)")
    print("=" * 70)
    print()
    print("⚙️  S3优化配置:")
    print("   单笔金额: $12-15 USDC")
    print("   交易间隔: 15-45 分钟")
    print("   目标市场: <6h, 胜率>95%")
    print("   日目标: 20-50笔, volume $500-1000")
    print("   成本监控: 启用")
    print()
    print("💡 原理: 频繁小额交易 → 赚取积分 → 潜在空投")
    print()
    print("⚠️  按 Ctrl+C 停止")
    print("=" * 70)
    print()
    
    # 配置策略 (S3优化版)
    config = {
        "base_trade_size": 12,      # $12 最优
        "max_trade_size": 15,       # $15 上限
        "min_interval": 15,         # 15分钟
        "max_interval": 45,         # 45分钟
        "max_time_remaining": 6,    # 最大6小时
        "min_win_rate": 0.95,       # 胜率>95%
        "prefer_crypto": True,      # 优先Crypto
        "order_lifetime": 300,      # 5分钟
        "snipe_pause_threshold": 10,
        "snipe_pause_duration": 300,
        "max_gas_cost_usd": 0.5,
        "min_profit_margin": 0.001
    }
    
    strategy = AntiSnipeMarketMaker(platform, config)
    
    try:
        await strategy.run()
    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("⏹️  策略已停止")
        print("=" * 70)
        
        # 显示统计
        stats = strategy.get_stats()
        print(f"\n📊 最终统计:")
        print(f"   交易次数: {stats['trades']}")
        print(f"   总交易量: {stats['volume']} USDC")
        print(f"   被狙击: {stats['sniped_count']} 次")
        print(f"   暂停: {stats['paused_count']} 次")
        print(f"   跳过(成本): {stats['skipped_for_cost']} 次")
        
        # 再次查询积分 (可能失败)
        try:
            balance = await platform.get_balance()
            print(f"\n💎 当前积分: {balance['points']}")
        except:
            pass
    
    await platform.close()


if __name__ == "__main__":
    asyncio.run(main())
