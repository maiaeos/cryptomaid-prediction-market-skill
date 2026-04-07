#!/usr/bin/env python3
"""
半自动刷量助手 v2 - 增强版
- 每日目标进度
- 推荐逻辑说明
- 持仓监控
"""
import asyncio
import sys
sys.path.insert(0, '.')

import os
import json
from decimal import Decimal
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

from platforms.limitless_full import LimitlessPlatform

# 每日目标配置
DAILY_TARGET = {
    "trades": 30,      # 30笔
    "volume": 500,     # $500
    "max_loss": 10     # $10 最大亏损
}

# 数据文件
DATA_FILE = ".farming_data.json"

def load_daily_data():
    """加载今日数据"""
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            # 检查是否是今天的数据
            if data.get('date') == str(date.today()):
                return data
    except:
        pass
    
    # 初始化今日数据
    return {
        "date": str(date.today()),
        "trades": 0,
        "volume": 0,
        "positions": []
    }

def save_daily_data(data):
    """保存今日数据"""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def print_progress(current, target, label):
    """打印进度条"""
    pct = min(current / target * 100, 100)
    bar_len = 20
    filled = int(bar_len * pct / 100)
    bar = '█' * filled + '░' * (bar_len - filled)
    print(f"   {label}: [{bar}] {current:.0f}/{target} ({pct:.1f}%)")

print('='*70)
print('🚀 Limitless S3 半自动刷量助手 v2')
print('='*70)
print()

async def main():
    api_key = os.getenv('LIMITLESS_API_KEY')
    wallet_address = os.getenv('LIMITLESS_ACCOUNT_ADDRESS')
    
    if not api_key or not wallet_address:
        print('❌ 请设置 API Key 和钱包地址')
        return
    
    # 加载今日数据
    daily_data = load_daily_data()
    
    print('📊 今日目标进度:')
    print_progress(daily_data['trades'], DAILY_TARGET['trades'], '交易笔数')
    print_progress(daily_data['volume'], DAILY_TARGET['volume'], '交易量')
    print()
    
    platform = LimitlessPlatform(api_key=api_key, wallet_address=wallet_address)
    
    print('📡 获取市场数据...')
    markets = await platform.get_all_markets()
    print(f'✅ 获取到 {len(markets)} 个市场')
    print()
    
    # 获取当前持仓
    print('📈 检查当前持仓...')
    # TODO: 获取实际持仓
    print(f'   当前持仓: {len(daily_data.get("positions", []))} 个市场')
    print()
    
    # S3筛选: 短周期优先 (<6h)
    print('🔍 分析市场 (S3策略: 短周期<6h + 高流动性)...')
    
    good_markets = []
    now = datetime.now()
    
    for m in markets:
        if not m.expires_at:
            continue
            
        time_remaining_hours = (m.expires_at - now).total_seconds() / 3600
        
        # 筛选条件
        if time_remaining_hours > 6 or time_remaining_hours < 0.5:
            continue
        
        yes_price = float(m.yes_price) if m.yes_price else 0.5
        no_price = float(m.no_price) if m.no_price else 0.5
        
        # 选择方向（选价格高的，胜率更高）
        if yes_price > no_price:
            direction = 'YES'
            win_rate = yes_price
            price = yes_price
        else:
            direction = 'NO'
            win_rate = no_price
            price = no_price
        
        liquidity = float(m.liquidity) if m.liquidity else 0
        
        # S3评分算法
        score = 0
        score += (6 - time_remaining_hours) * 15        # 时间越短越好
        score += win_rate * 30                          # 胜率越高越好
        score += min(liquidity / 100, 20)              # 流动性加分
        
        # 推荐理由
        reasons = []
        if time_remaining_hours < 2:
            reasons.append("⏰ 即将结算")
        if win_rate > 0.7:
            reasons.append(f"🎯 胜率{win_rate*100:.0f}%")
        if liquidity > 1000:
            reasons.append("💧 流动性好")
        
        good_markets.append({
            'market': m,
            'direction': direction,
            'win_rate': win_rate,
            'price': price,
            'time_remaining': time_remaining_hours,
            'score': score,
            'liquidity': liquidity,
            'reasons': reasons
        })
    
    good_markets.sort(key=lambda x: x['score'], reverse=True)
    
    if not good_markets:
        print('❌ 当前没有合适的短周期市场')
        print('   建议: 等待新的市场开放')
        return
    
    print(f'✅ 找到 {len(good_markets)} 个优质市场')
    print()
    
    # 显示推荐
    print('🎯 推荐市场 (按S3评分排序):')
    print()
    
    for i, gm in enumerate(good_markets[:5], 1):
        m = gm['market']
        print(f"{i}. {m.question[:45]}...")
        print(f"   推荐: {gm['direction']} @ {gm['price']*100:.1f}¢ (胜率{gm['win_rate']*100:.0f}%)")
        print(f"   剩余: {gm['time_remaining']:.1f}h | 评分: {gm['score']:.0f}")
        print(f"   理由: {' | '.join(gm['reasons'])}")
        print()
    
    # 推荐最佳
    best = good_markets[0]
    print('='*70)
    print('⭐ 最佳推荐:')
    print(f"   市场: {best['market'].question}")
    print(f"   操作: 买 {best['direction']} @ {best['price']*100:.1f}¢")
    print(f"   胜率: {best['win_rate']*100:.1f}%")
    print(f"   剩余: {best['time_remaining']:.1f}h (约{best['time_remaining']*60:.0f}分钟)")
    print(f"   建议: $12 USDC")
    print()
    print('   💡 策略逻辑:')
    print('      - 短周期: 快速结算，资金效率高')
    print('      - 高胜率: 价格极端，亏损概率低')
    print('      - 刷积分: 每笔交易都赚积分')
    print('='*70)
    print()
    
    # 生成交易链接并自动打开
    market_slug = best['market'].slug
    trade_url = f"https://limitless.exchange/markets/{market_slug}"
    
    print('📱 正在打开交易页面...')
    print(f'   链接: {trade_url}')
    print()
    
    # 尝试自动打开浏览器
    try:
        import subprocess
        import platform as pf
        
        system = pf.system()
        if system == 'Darwin':
            subprocess.Popen(['open', trade_url])
        elif system == 'Linux':
            subprocess.Popen(['xdg-open', trade_url])
        elif system == 'Windows':
            subprocess.Popen(['start', trade_url], shell=True)
        
        print('✅ 浏览器已自动打开')
    except Exception as e:
        print(f'⚠️  自动打开失败: {e}')
    
    print()
    print('操作步骤:')
    print(f"   1. 点击 '{best['direction']}' 按钮")
    print('   2. 输入金额: $12')
    print('   3. 点击确认 (OneKey自动签名)')
    print()
    print('⏰ 平仓提醒:')
    print(f"   市场将在 {best['time_remaining']:.1f}h 后自动结算")
    print('   无需手动平仓，到期自动结算')
    print()
    
    # 询问是否完成
    response = input('是否已完成交易? (y/n): ')
    
    if response.lower() == 'y':
        # 更新今日数据
        daily_data['trades'] += 1
        daily_data['volume'] += 12
        daily_data['positions'].append({
            'market': best['market'].question,
            'direction': best['direction'],
            'amount': 12,
            'time': str(datetime.now()),
            'expires': str(best['market'].expires_at)
        })
        save_daily_data(daily_data)
        
        print()
        print('✅ 交易已记录!')
        print()
        print('📊 更新后进度:')
        print_progress(daily_data['trades'], DAILY_TARGET['trades'], '交易笔数')
        print_progress(daily_data['volume'], DAILY_TARGET['volume'], '交易量')
        print()
        
        # 计算还需多少笔
        remaining_trades = DAILY_TARGET['trades'] - daily_data['trades']
        remaining_volume = DAILY_TARGET['volume'] - daily_data['volume']
        
        if remaining_trades > 0:
            print(f'💪 还需 {remaining_trades} 笔，约 {remaining_volume:.0f} USDC 完成今日目标')
        else:
            print('🎉 今日目标已达成!')
    else:
        print('⏸️  已暂停')
    
    await platform.close()
    print()
    print('='*70)

if __name__ == "__main__":
    asyncio.run(main())
