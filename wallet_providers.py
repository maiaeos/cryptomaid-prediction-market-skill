"""
私钥钱包实现
支持直接私钥签名，无需硬件钱包
"""

import json
from decimal import Decimal
from typing import Dict, Optional
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from wallet_base import BaseWallet


class PrivateKeyWallet(BaseWallet):
    """私钥钱包 - 软件钱包实现"""
    
    def __init__(self, private_key: str, rpc_url: str = "https://mainnet.base.org"):
        super().__init__("private_key")
        
        # 确保私钥格式正确
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
        
        self.private_key = private_key
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        
        # Web3 连接
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        self.connected = True  # 私钥钱包立即连接
        print(f"✅ 私钥钱包: {self.address}")
    
    async def connect(self) -> bool:
        """私钥钱包无需连接步骤"""
        return True
    
    async def get_address(self) -> Optional[str]:
        return self.address
    
    async def sign_transaction(self, tx_data: Dict) -> Dict:
        """
        签名交易
        
        tx_data 格式:
        {
            "platform": "limitless" | "polymarket",
            "chain_id": 8453 | 137,
            "to": "0x...",
            "data": "0x...",
            "value": 0,
            "gas": 200000,
            "maxFeePerGas": 1000000000,
            "maxPriorityFeePerGas": 100000000
        }
        """
        try:
            # 构建交易
            transaction = {
                "to": Web3.to_checksum_address(tx_data["to"]),
                "data": tx_data.get("data", "0x"),
                "value": tx_data.get("value", 0),
                "gas": tx_data.get("gas", 200000),
                "maxFeePerGas": tx_data.get("maxFeePerGas", self.w3.to_wei("1", "gwei")),
                "maxPriorityFeePerGas": tx_data.get("maxPriorityFeePerGas", self.w3.to_wei("0.1", "gwei")),
                "nonce": self.w3.eth.get_transaction_count(self.address),
                "chainId": tx_data.get("chain_id", 8453),
                "type": 2  # EIP-1559
            }
            
            # 签名交易
            signed = self.account.sign_transaction(transaction)
            
            # 发送交易
            tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
            
            return {
                "success": True,
                "signature": signed.signature.hex(),
                "tx_hash": tx_hash.hex(),
                "tx_data": transaction
            }
            
        except Exception as e:
            print(f"❌ 签名失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_balance(self, token: str = "ETH") -> Decimal:
        """获取余额"""
        if token == "ETH":
            balance_wei = self.w3.eth.get_balance(self.address)
            return Decimal(self.w3.from_wei(balance_wei, "ether"))
        else:
            # ERC20 代币余额查询
            # 需要代币合约地址
            return Decimal("0")
    
    async def sign_message(self, message: str) -> str:
        """签名消息 (用于 Limitless API 认证)"""
        message_encoded = encode_defunct(text=message)
        signed_message = self.account.sign_message(message_encoded)
        return signed_message.signature.hex()


class MetaMaskWallet(BaseWallet):
    """MetaMask/浏览器钱包 - 通过 WalletConnect"""
    
    def __init__(self, wallet_connect_uri: Optional[str] = None):
        super().__init__("metamask")
        self.wallet_connect_uri = wallet_connect_uri
        self.session = None
    
    async def connect(self) -> bool:
        """通过 WalletConnect 连接"""
        try:
            # 这里简化实现，实际使用 WalletConnect 库
            print("🔗 请使用 MetaMask 扫描二维码或点击连接")
            print(f"WalletConnect URI: {self.wallet_connect_uri}")
            
            # 模拟连接成功
            # 实际实现需要异步等待用户确认
            self.connected = True
            self.address = "0x..."  # 从 WalletConnect 获取
            return True
            
        except Exception as e:
            print(f"❌ MetaMask 连接失败: {e}")
            return False
    
    async def get_address(self) -> Optional[str]:
        return self.address
    
    async def sign_transaction(self, tx_data: Dict) -> Dict:
        """通过 WalletConnect 请求签名"""
        # 实际实现需要调用 WalletConnect API
        # 这里返回模拟数据
        return {
            "success": True,
            "signature": "0x...",
            "tx_hash": "0x..."
        }
    
    async def get_balance(self, token: str = "ETH") -> Decimal:
        return Decimal("0")
