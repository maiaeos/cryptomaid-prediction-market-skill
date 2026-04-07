# Prediction Arbitrage v1.0

预测市场三平台套利引擎 - 防狙击做市策略

## 🚀 快速开始

### 安装
```bash
openclaw skill install https://github.com/animaia/prediction-arbitrage.git
```

### 配置
1. 获取 Limitless API Key: https://limitless.exchange/settings/api
2. 准备 Base 链 ETH (Gas) 和 USDC (本金)
3. 编辑 `.env` 文件

### 运行
```bash
openclaw skill run prediction-arbitrage
```

## ✨ 功能

- ✅ 防狙击做市策略 (小单/随机/不暴露模式)
- ✅ 自动暂停机制 (被狙击频繁时暂停)
- ✅ 成本监控 (Gas过高时跳过)
- ✅ 多钱包支持 (私钥/OneKey/MetaMask)
- ✅ Limitless 完整交易接口

## 📖 文档

- [快速开始](docs/QUICK_START.md)
- [用户指南](docs/USER_GUIDE.md)
- [测试指南](docs/TESTER_GUIDE.md)

## ⚠️ 风险提示

- 可能损失 Gas 费
- 需要小额测试 ($50-200)
- 私钥只保存在本地

## 📝 License

MIT
