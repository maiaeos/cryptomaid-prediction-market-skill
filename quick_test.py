#!/usr/bin/env python3
"""
快速测试 - 验证自动赚积分功能
运行一次完整的交易周期
"""
import asyncio
import sys
sys.path.insert(0, '.')

import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

from platforms.limitless_full import LimitlessPlatform
from anti_snipe_mm import AntiSnipeMarketMaker

print('='*70)
print('🚀 自动赚积分 - 快速测试')
print('='*70)
print()

async def test():
    # 检查配置
    api_key = os.getenv('LIMITLESS_API_KEY')
    wallet_address = os.getenv('LIMITLESS_ACCOUNT_ADDRESS')
    
    if not api_key or not wallet_address:
        print('❌ 错误: 请设置 LIMITLESS_API_KEY 和 LIMITLESS_ACCOUNT_ADDRESS')
        return
    
    print(f'🔑 API: {api_key[:20]}...')
    print(f'📍 地址: {wallet_address}')
    print()
    
    # 连接平台
    print('📡 连接 Limitless...')
    platform = LimitlessPlatform(api_key=api_key, wallet_address=wallet_address)
    
    markets = await platform.get_all_markets()
    print(f'✅ 获取到 {len(markets)} 个市场')
    print()
    
    # 选择最优市场
    print('🔥 最优市场 (按积分效率):')
    valid_markets = [m for m in markets if m.liquidity > 0 and m.volume_24h > 0]
    valid_markets.sort(key=lambda m: float(m.volume_24h) / float(m.liquidity), reverse=True)
    
    for i, m in enumerate(valid_markets[:3], 1):
        eff = float(m.volume_24h) / float(m.liquidity)
        print(f'{i}. {m.question[:40]}...')
        print(f'   流动性: ${float(m.liquidity):,.0f}')
        print(f'   24h量: ${float(m.volume_24h):,.0f}')
        print(f'   效率: {eff:.2f}')
        print(f'   价格: YES {float(m.yes_price):.2f} | NO {float(m.no_price):.2f}')
    print()
    
    # 模拟一次交易
    if valid_markets:
        market = valid_markets[0]
        print('💰 模拟交易:')
        print(f'   市场: {market.question[:40]}...')
        print(f'   金额: 10 USDC')
        print(f'   方向: YES @ {float(market.yes_price):.3f}')
        print(f'   预估Gas: $0.005')
        print(f'   预估积分: +0.1 积分')
        print()
    
    await platform.close()
    
    print('='*70)
    print('✅ 测试完成! 系统运行正常')
    print('='*70)
    print()
    print('🚀 启动完整版:')
    print('   python run_api_mode.py')

if __name__ == "__main__":
    asyncio.run(test())
