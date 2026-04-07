"""
钱包管理器 - 抽象基类
支持多种钱包类型: OneKey, 私钥, Web3
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal


class BaseWallet(ABC):
    """钱包抽象基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.address: Optional[str] = None
        self.connected = False
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接钱包，返回是否成功"""
        pass
    
    @abstractmethod
    async def get_address(self) -> Optional[str]:
        """获取钱包地址"""
        pass
    
    @abstractmethod
    async def sign_transaction(self, tx_data: Dict) -> Dict:
        """
        签名交易
        返回: {
            "success": bool,
            "signature": str,
            "tx_hash": str (可选)
        }
        """
        pass
    
    @abstractmethod
    async def get_balance(self, token: str = "ETH") -> Decimal:
        """获取代币余额"""
        pass
    
    def is_connected(self) -> bool:
        return self.connected


class WalletManager:
    """钱包管理器 - 统一管理多个钱包"""
    
    def __init__(self):
        self.wallets: Dict[str, BaseWallet] = {}
        self.default_wallet: Optional[str] = None
    
    def register_wallet(self, name: str, wallet: BaseWallet):
        """注册钱包"""
        self.wallets[name] = wallet
        if self.default_wallet is None:
            self.default_wallet = name
    
    def get_wallet(self, name: Optional[str] = None) -> Optional[BaseWallet]:
        """获取钱包实例"""
        name = name or self.default_wallet
        return self.wallets.get(name)
    
    async def connect_all(self) -> Dict[str, bool]:
        """连接所有钱包"""
        results = {}
        for name, wallet in self.wallets.items():
            results[name] = await wallet.connect()
        return results
    
    def get_status(self) -> Dict:
        """获取所有钱包状态"""
        return {
            name: {
                "connected": w.is_connected(),
                "address": w.address
            }
            for name, w in self.wallets.items()
        }
