# Prediction Arbitrage Skill v1.0 🚀

**发布日期**: 2025-04-07
**版本**: v1.0.0
**状态**: 可用版本

---

## ✨ 功能特性

### 1. 防狙击做市策略
- ✅ **小单分散**: 10-30 USDC 随机金额
- ✅ **随机化**: 时间/价格/数量/模式都随机
- ✅ **不暴露模式**: 无固定规律
- ✅ **快速撤单**: 60秒存活，超时自动取消
- ✅ **狙击检测**: 10秒内完全成交检测
- ✅ **自动暂停**: 被狙击频繁时自动暂停10分钟
- ✅ **成本监控**: Gas成本过高时跳过交易

### 2. 多钱包支持
- ✅ **私钥钱包**: 软件钱包，无需硬件
- ✅ **OneKey**: 硬件钱包支持
- ✅ **MetaMask**: WalletConnect 连接

### 3. 平台集成
- ✅ **Limitless**: 完整交易接口
- ⚠️ **Polymarket**: 读取接口 (交易待完善)
- ⚠️ **Predict.fun**: 框架 (待接入)

### 4. 套利功能
- ✅ **三平台扫描**: 价格聚合
- ✅ **机会计算**: 利润预估
- ⚠️ **自动执行**: 需要完善

---

## 🚀 快速开始

### 1. 安装
```bash
cd ~/.openclaw/workspace/skills/prediction-arbitrage
pip install -r requirements.txt
```

### 2. 配置
```bash
cp .env.example .env
# 编辑 .env
```

**.env 示例**:
```bash
# Limitless (必需)
LIMITLESS_API_KEY=lmts_live_xxxxxx
LIMITLESS_ACCOUNT_ADDRESS=0xYourAddress

# 私钥 (可选，用于交易)
PRIVATE_KEY=0xYourPrivateKey

# OneKey (可选)
ONEKEY_ENABLED=false
ONEKEY_BRIDGE_URL=http://localhost:21320

# Telegram (可选)
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

### 3. 启动做市
```bash
# 防狙击做市
python run_mm.py
```

---

## 📊 使用场景

### 场景 1: 刷量赚积分
```python
config = {
    "base_trade_size": 10,      # 基础金额 10 USDC
    "max_trade_size": 30,       # 最大 30 USDC
    "min_interval": 30,         # 最少 30 秒间隔
    "max_interval": 120,        # 最多 120 秒间隔
    "snipe_pause_threshold": 5, # 5次狙击暂停
    "max_gas_cost_usd": 1.0     # Gas 成本限制 $1
}
```

### 场景 2: 保守做市
```python
config = {
    "base_trade_size": 50,      # 较大金额
    "price_variance": 0.01,     # 更大价格偏离
    "order_lifetime": 120,      # 更长存活时间
    "min_profit_margin": 0.005  # 更高利润要求
}
```

---

## 🛡️ 防狙击机制

### 自动暂停
```
条件: 被狙击 >= 5次 且 狙击率 > 30%
动作: 自动暂停 10 分钟
恢复: 暂停结束后重置统计
```

### 成本监控
```
检查: 每笔交易前预估 Gas 成本
跳过: Gas > $1 或 利润 < 0.2%
记录: 累计 Gas 成本和预估利润
```

### 随机化策略
```
时间: 30-120 秒随机
金额: 基础 ±20%
价格: 基础 ±0.5%
模式: 50% 双边 / 50% 单边随机
市场: 从合适市场中随机选择
```

---

## 📈 监控指标

运行时会显示:
```
📊 统计: 25 笔, 680 USDC, 被狙击: 2
⏳ 等待 45s 后下次交易...
```

最终统计:
```
交易次数: 100
总交易量: 2,450 USDC
被狙击: 5 (5%)
取消订单: 12 (12%)
暂停次数: 1
跳过(成本): 3
预估净利润: $12.5
```

---

## ⚠️ 风险提示

1. **资金风险**: 建议小额测试 ($100-500)
2. **Gas 成本**: Base 链 Gas 低，但频繁交易累积
3. **市场流动性**: 低流动性市场可能无法成交
4. **平台风险**: 智能合约漏洞、平台停机

---

## 🔧 故障排除

### 问题 1: API 连接失败
```bash
# 检查 API Key
python -c "
from platforms.limitless_full import LimitlessPlatform
import asyncio
p = LimitlessPlatform('your-api-key', '0x...')
asyncio.run(p.get_all_markets())
"
```

### 问题 2: 交易失败
- 检查私钥是否正确
- 检查 Base 链是否有 ETH 支付 Gas
- 检查 USDC 余额是否充足

### 问题 3: 被狙击频繁
- 降低 `base_trade_size`
- 增加 `price_variance`
- 调整 `snipe_pause_threshold`

---

## 📁 文件结构

```
skills/prediction-arbitrage/
├── README.md                 # 项目说明
├── SKILL.md                  # Skill 定义
├── requirements.txt          # 依赖
├── .env                      # 配置 (用户填写)
├── .env.example              # 配置示例
│
├── arbitrage_engine.py       # 套利引擎核心
├── cli.py                    # 命令行界面
├── farming_strategies.py     # 基础策略
├── anti_snipe_mm.py          # ⭐ 防狙击做市
├── telegram_notifier.py      # Telegram 通知
│
├── wallet_base.py            # 钱包基类
├── wallet_providers.py       # 私钥/MetaMask
├── wallet_onekey.py          # OneKey 支持
│
├── platforms/
│   ├── base.py               # 平台基类
│   ├── limitless_full.py     # ⭐ Limitless 完整实现
│   ├── polymarket.py         # Polymarket
│   └── predict_fun.py        # Predict.fun
│
└── run_mm.py                 # ⭐ 一键启动脚本
```

---

## 🗺️ 路线图

### v1.0 (当前)
- ✅ 防狙击做市 (Limitless)
- ✅ 多钱包支持
- ✅ 自动暂停/成本监控

### v1.1 (计划)
- 🔄 Polymarket 交易执行
- 🔄 套利自动执行
- 🔄 动态参数调整
- 🔄 多账户支持

### v2.0 (远期)
- 📋 机器学习优化
- 📋 可视化监控面板
- 📋 跨平台组合策略

---

## 📝 更新日志

### v1.0.0 (2025-04-07)
- 初始发布
- 防狙击做市策略
- 多钱包支持
- 自动暂停和成本监控
- Limitless 完整交易接口

---

## 🤝 贡献

欢迎提交 Issue 和 PR!

---

## 📄 License

MIT

---

**🎉 v1.0 发布完成！开始你的做市之旅吧！**
