#!/usr/bin/env python3
"""
自动赚积分测试
演示如何在 Limitless 刷量赚积分
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
print('🎯 自动赚积分测试')
print('='*70)
print()
print('原理:')
print('  1. 在 Limitless 频繁小额交易')
print('  2. 赚取交易量积分')
print('  3. 积分可能用于未来空投')
print('  4. 防狙击策略保护资金')
print()

async def test_volume_farming():
    """测试刷量赚积分"""
    
    # 检查配置
    api_key = os.getenv('LIMITLESS_API_KEY')
    if not api_key:
        print('❌ 错误: 未设置 LIMITLESS_API_KEY')
        print('   请编辑 .env 文件添加')
        return
    
    # 创建平台连接
    print('🔌 连接 Limitless...')
    platform = LimitlessPlatform(
        api_key=api_key,
        wallet_address='0xB97b9F2057A8B49F57c2D51916F9179157828a5f'
    )
    
    # 获取当前积分
    try:
        balance = await platform.get_balance()
        current_points = balance.get('points', Decimal('0'))
        print(f'💰 当前积分: {current_points}')
        print(f'   USDC 余额: {balance["USDC"]}')
        print()
    except Exception as e:
        print(f'⚠️  获取余额失败: {e}')
        current_points = Decimal('0')
    
    # 配置刷量策略
    print('⚙️  配置刷量策略...')
    config = {
        'base_trade_size': 10,      # 每笔 10 USDC
        'max_trade_size': 20,       # 最大 20 USDC
        'min_interval': 30,         # 最少 30 秒间隔
        'max_interval': 60,         # 最多 60 秒间隔
        'order_lifetime': 60,       # 订单存活 60 秒
        'snipe_pause_threshold': 5, # 5次狙击暂停
        'snipe_pause_duration': 300,# 暂停 5 分钟
        'max_gas_cost_usd': 1.0,    # Gas 限制 $1
        'min_profit_margin': 0.001  # 最小利润 0.1%
    }
    
    print(f'   基础金额: {config["base_trade_size"]} USDC')
    print(f'   随机间隔: {config["min_interval"]}-{config["max_interval"]} 秒')
    print(f'   预估日交易量: ~$10,000-20,000')
    print()
    
    # 检查是否有私钥
    private_key = os.getenv('PRIVATE_KEY')
    if private_key:
        print('✅ 检测到私钥，可以执行真实交易')
        print('   ⚠️  这将使用真实资金进行交易')
        print()
        
        response = input('是否开始真实交易? (yes/no): ')
        if response.lower() != 'yes':
            print('❌ 已取消')
            await platform.close()
            return
    else:
        print('⚠️  未检测到私钥，只能模拟运行')
        print('   如需真实交易，请设置 PRIVATE_KEY')
        print()
    
    # 创建策略
    strategy = AntiSnipeMarketMaker(platform, config)
    
    print('🚀 启动刷量策略...')
    print('   按 Ctrl+C 停止')
    print('='*70)
    print()
    
    try:
        # 运行策略
        await strategy.run()
    except KeyboardInterrupt:
        print('\n\n' + '='*70)
        print('⏹️  策略已停止')
        print('='*70)
        
        # 显示统计
        stats = strategy.get_stats()
        print(f'\n📊 最终统计:')
        print(f'   交易次数: {stats["trades"]}')
        print(f'   总交易量: {stats["volume"]} USDC')
        print(f'   被狙击: {stats["sniped_count"]} 次')
        print(f'   暂停: {stats["paused_count"]} 次')
        print(f'   跳过(成本): {stats["skipped_for_cost"]} 次')
        print(f'   预估 Gas 成本: ${stats["total_gas_cost"]}')
        
        # 再次查询积分
        try:
            balance = await platform.get_balance()
            new_points = balance.get('points', Decimal('0'))
            earned = new_points - current_points
            print(f'\n💎 积分变化:')
            print(f'   之前: {current_points}')
            print(f'   之后: {new_points}')
            print(f'   赚取: +{earned} 积分')
        except:
            pass
    
    await platform.close()

if __name__ == "__main__":
    asyncio.run(test_volume_farming())
