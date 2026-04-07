"""
Telegram 套利机会推送
支持通知和确认按钮
"""

import asyncio
from typing import Optional
from decimal import Decimal


class TelegramNotifier:
    """Telegram 套利通知器"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """发送普通消息"""
        try:
            import aiohttp
            
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    if result.get("ok"):
                        print("✅ Telegram: 消息已发送")
                        return True
                    else:
                        print(f"❌ Telegram: 发送失败 {result}")
                        return False
                        
        except Exception as e:
            print(f"❌ Telegram: 发送失败: {e}")
            return False
    
    async def send_arbitrage_alert(self, opp: dict) -> bool:
        """
        发送套利机会通知
        
        包含确认按钮，主人点击后触发 OneKey 签名
        """
        try:
            import aiohttp
            
            # 构建消息
            message = self._format_arbitrage_message(opp)
            
            # 构建内联键盘
            keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ 确认执行套利",
                            "callback_data": f"execute_arb:{opp.get('id', '0')}"
                        },
                        {
                            "text": "❌ 忽略",
                            "callback_data": f"ignore_arb:{opp.get('id', '0')}"
                        }
                    ],
                    [
                        {
                            "text": "📊 查看市场",
                            "url": opp.get("market_url", "https://limitless.exchange")
                        }
                    ]
                ]
            }
            
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload
                ) as resp:
                    result = await resp.json()
                    if result.get("ok"):
                        print("✅ Telegram: 套利通知已发送")
                        return True
                    else:
                        print(f"❌ Telegram: 发送失败 {result}")
                        return False
                        
        except Exception as e:
            print(f"❌ Telegram: 发送失败: {e}")
            return False
    
    def _format_arbitrage_message(self, opp: dict) -> str:
        """格式化套利消息"""
        profit_pct = float(opp.get("profit_pct", 0)) * 100
        profit = float(opp.get("profit", 0))
        
        # 利润颜色
        if profit_pct >= 2:
            profit_emoji = "🚀"
        elif profit_pct >= 1:
            profit_emoji = "🔥"
        else:
            profit_emoji = "💰"
        
        message = f"""
{profit_emoji} **套利机会发现！** {profit_emoji}

**市场**: {opp.get('question', 'Unknown')[:100]}

**套利策略**:
├ {opp.get('platform_a', 'A')}: 买 YES @ ${float(opp.get('yes_price_a', 0)):.4f}
└ {opp.get('platform_b', 'B')}: 买 NO @ ${float(opp.get('no_price_b', 0)):.4f}

**收益分析**:
├ 总成本: ${float(opp.get('total_cost', 0)):.4f}
├ 手续费: ${float(opp.get('fees', 0)):.4f}
├ 净利润: ${profit:.4f}
└ 利润率: **{profit_pct:.2f}%**

⏰ {opp.get('timestamp', 'Now')}

⚠️ *请在 30 秒内确认，价格可能变化*
"""
        return message
    
    async def send_execution_result(self, success: bool, details: dict) -> bool:
        """发送执行结果"""
        if success:
            message = f"""
✅ **套利执行成功！**

市场: {details.get('question', 'Unknown')[:60]}...

执行详情:
├ {details.get('platform_a')}: {details.get('result_a', 'OK')}
└ {details.get('platform_b')}: {details.get('result_b', 'OK')}

利润: ${float(details.get('profit', 0)):.4f}
"""
        else:
            message = f"""
❌ **套利执行失败**

市场: {details.get('question', 'Unknown')[:60]}...

错误: {details.get('error', 'Unknown error')}

建议: 请检查余额和网络状态
"""
        
        return await self.send_message(message)
    
    async def send_balance_alert(self, platform: str, balance: Decimal, threshold: Decimal) -> bool:
        """发送余额不足警告"""
        message = f"""
⚠️ **余额不足警告**

平台: {platform}
当前余额: ${float(balance):.2f}
警告阈值: ${float(threshold):.2f}

请及时充值以避免错过套利机会
"""
        return await self.send_message(message)
    
    async def send_error_alert(self, error_message: str) -> bool:
        """发送错误警告"""
        message = f"""
🚨 **系统错误**

{error_message}

请检查系统日志
"""
        return await self.send_message(message)


# 模拟模式
class TelegramSimulator(TelegramNotifier):
    """Telegram 模拟器 (用于开发和测试)"""
    
    def __init__(self):
        super().__init__("simulated_token", "simulated_chat")
    
    async def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        print("\n" + "=" * 60)
        print("🔔 Telegram 模拟通知:")
        print("=" * 60)
        print(text)
        print("=" * 60 + "\n")
        return True
    
    async def send_arbitrage_alert(self, opp: dict) -> bool:
        print("\n" + "=" * 60)
        print("🎯 Telegram 模拟 - 套利机会:")
        print("=" * 60)
        print(self._format_arbitrage_message(opp))
        print("[按钮: ✅ 确认执行套利 | ❌ 忽略]")
        print("=" * 60 + "\n")
        
        # 模拟用户确认 (3秒后自动确认)
        await asyncio.sleep(3)
        print("🔧 模拟: 用户已确认")
        return True
