#!/usr/bin/env python3
"""
半自动刷量助手 - 优化用户体验 (S3优化版)
我帮你选市场，你只需确认交易
"""
import asyncio
import sys
sys.path.insert(0, '.')

import os
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from platforms.limitless_full import LimitlessPlatform

print('='*70)
print('🚀 Limitless S3 半自动刷量助手')
print('='*70)
print()
print('流程: 我推荐市场 → 打开交易窗口 → 你确认金额 → OneKey签名')
print()

async def main():
    api_key = os.getenv('LIMITLESS_API_KEY')
    wallet_address = os.getenv('LIMITLESS_ACCOUNT_ADDRESS')
    
    if not api_key or not wallet_address:
        print('❌ 请设置 API Key 和钱包地址')
        return
    
    platform = LimitlessPlatform(api_key=api_key, wallet_address=wallet_address)
    
    print('📡 获取市场数据...')
    markets = await platform.get_all_markets()
    print(f'✅ 获取到 {len(markets)} 个市场')
    print()
    
    # S3筛选: 短周期优先 (<6h)
    print('🔍 筛选短周期市场 (<6h)...')
    
    good_markets = []
    now = datetime.now()
    
    for m in markets:
        # 计算剩余时间
        if m.expires_at:
            time_remaining_hours = (m.expires_at - now).total_seconds() / 3600
        else:
            continue
        
        # 只筛选短周期 (30分钟 - 6小时)
        if time_remaining_hours > 6 or time_remaining_hours < 0.5:
            continue
        
        yes_price = float(m.yes_price) if m.yes_price else 0.5
        no_price = float(m.no_price) if m.no_price else 0.5
        
        # 选择方向（优先选价格高的方向）
        if yes_price > no_price:
            direction = 'YES'
            win_rate = yes_price
        else:
            direction = 'NO'
            win_rate = no_price
        
        # 检查流动性 (API返回可能有问题，暂时跳过)
        liquidity = float(m.liquidity) if m.liquidity else 0
        # if liquidity < 100:
        #     continue
        
        # 打分：时间越短越好 + 胜率越高越好
        score = (6 - time_remaining_hours) * 10 + win_rate * 50
        
        good_markets.append({
            'market': m,
            'direction': direction,
            'win_rate': win_rate,
            'time_remaining': time_remaining_hours,
            'score': score,
            'liquidity': liquidity
        })
    
    # 排序
    good_markets.sort(key=lambda x: x['score'], reverse=True)
    
    if not good_markets:
        print('❌ 当前没有短周期市场 (<6h)')
        print('   建议: 等待新的短周期市场开放')
        print('   或查看 >6h 的市场')
        return
    
    print(f'✅ 找到 {len(good_markets)} 个短周期市场')
    print()
    
    # 显示推荐
    print('🎯 推荐市场 (按质量排序):')
    print()
    
    for i, gm in enumerate(good_markets[:5], 1):
        m = gm['market']
        print(f"{i}. {m.question[:50]}...")
        print(f"   方向: {gm['direction']} | 胜率: {gm['win_rate']*100:.1f}%")
        print(f"   剩余: {gm['time_remaining']:.1f}h | 流动性: ${gm['liquidity']:,.0f}")
        print(f"   价格: YES {float(m.yes_price)*100:.1f}¢ | NO {float(m.no_price)*100:.1f}¢")
        print()
    
    # 推荐最佳
    best = good_markets[0]
    print('='*70)
    print('⭐ 最佳推荐:')
    print(f"   市场: {best['market'].question}")
    print(f"   方向: {best['direction']} (胜率 {best['win_rate']*100:.1f}%)")
    print(f"   剩余时间: {best['time_remaining']:.1f}h")
    print(f"   建议金额: $12 USDC")
    print('='*70)
    print()
    
    # 生成交易链接
    market_slug = best['market'].slug
    trade_url = f"https://limitless.exchange/markets/{market_slug}"
    
    print('📱 操作步骤:')
    print('   1. 点击下面的链接打开交易页面')
    print(f"   2. 选择 '{best['direction']}' 方向")
    print('   3. 输入金额: $12')
    print('   4. 点击确认，OneKey 自动签名')
    print()
    print(f'   链接: {trade_url}')
    print()
    
    # 询问是否继续
    response = input('是否已打开链接并完成交易? (y/n): ')
    
    if response.lower() == 'y':
        print()
        print('✅ 交易完成!')
        print()
        print('📊 统计:')
        print('   本笔: $12')
        print('   建议: 继续下一笔或查看 Portfolio')
        print()
        print('💡 提示: 每天目标 20-50 笔，volume $500-1000')
    else:
        print('⏸️  已暂停，随时可以继续')
    
    await platform.close()
    print()
    print('='*70)

if __name__ == "__main__":
    asyncio.run(main())
