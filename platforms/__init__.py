# platforms 包初始化
from .base import PredictionMarket, Market, Order, Position
from .limitless import LimitlessPlatform
from .polymarket import PolymarketPlatform
from .predict_fun import PredictFunPlatform

__all__ = [
    "PredictionMarket",
    "Market",
    "Order",
    "Position",
    "LimitlessPlatform",
    "PolymarketPlatform",
    "PredictFunPlatform",
]
