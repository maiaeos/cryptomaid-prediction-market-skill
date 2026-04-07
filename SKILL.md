---
name: prediction-arbitrage
description: |
  预测市场三平台套利引擎 (Limitless + Polymarket + Predict.fun)
  支持跨平台套利机会发现、OneKey 硬件钱包签名、Telegram 推送通知
  人工确认模式：发现机会 → 推送通知 → 指纹签名 → 自动执行
compatibility: Python 3.11+, OneKey Pro, Telegram Bot
---

# Prediction Arbitrage Engine

## 功能特性

- ✅ **三平台套利扫描**: Limitless, Polymarket, Predict.fun
- ✅ **OneKey Pro 集成**: 指纹签名，硬件级安全
- ✅ **实时推送**: Telegram 套利机会通知
- ✅ **人工确认模式**: 主人确认后才执行
- ✅ **风控系统**: 仓位限制、止损、断路器

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 和 Telegram Bot Token

# 运行套利扫描
python arbitrage_engine.py --scan

# 启动监控模式
python arbitrage_engine.py --monitor
```

## 架构

```
arbitrage_engine.py
├── 套利机会计算
├── 三平台价格聚合
├── 风控检查
└── 执行决策

platforms/
├── base.py          # 平台基类
├── limitless.py     # Limitless 集成
├── polymarket.py    # Polymarket 合约交互
└── predict_fun.py   # Predict.fun 集成

wallet_manager.py    # OneKey 硬件钱包
telegram_notifier.py # Telegram 推送
```

## 套利策略

### 跨平台套利

当同一事件在不同平台的价格差异 > 手续费时，存在套利机会。

**有效套利条件**:
```
Platform_A_YES + Platform_B_NO < 1.00 - fees
```

**示例**:
```
Limitless:  YES @ $0.45
Polymarket: NO  @ $0.48
--------------------------
总成本: $0.93
保证利润: $0.07 (7%)
```

## OneKey 签名流程

```
1. 发现套利机会
2. 发送 Telegram 通知
3. 主人点击"确认执行"
4. OneKey Pro 弹出签名请求
5. 主人指纹确认
6. 双边自动下单
```

## 配置

### 环境变量 (.env)

```bash
# Limitless
LIMITLESS_API_KEY=lmts_...

# Polymarket (合约交互)
POLYMARKET_RPC=https://polygon-rpc.com
POLYMARKET_PRIVATE_KEY=0x...  # OneKey 导出

# Predict.fun
PREDICT_FUN_API_KEY=...  # Discord 申请
PREDICT_FUN_RPC=https://bsc-dataseed.binance.org

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...

# OneKey
ONEKEY_BRIDGE_URL=http://localhost:21320
```

## 风险提示

1. **执行风险**: 两边不能同时成交可能导致单边敞口
2. **Gas 费**: 链上交易需要 MATIC (Polymarket) 或 BNB (Predict.fun)
3. **市场匹配**: 确保是同一事件，避免误套利
4. **流动性**: 低流动性市场可能无法完全成交

## License

MIT
