"""
backtest/execution.py
執行模型：手續費、滑價（不對稱）、漲跌停、部位上限
可獨立測試，不依賴其他模組
"""
from dataclasses import dataclass
from enum import Enum
from config.settings import EXECUTION


class Mode(Enum):
    IDEAL       = "ideal"
    REALISTIC   = "realistic"
    PESSIMISTIC = "pessimistic"


@dataclass
class Trade:
    stock_id:    str
    date:        str
    direction:   str    # "buy" | "sell"
    shares:      int
    raw_price:   float  # 原始成交價（收盤）
    mode:        str    # ideal | realistic | pessimistic

    # 計算後填入
    exec_price:  float = 0.0
    commission:  float = 0.0
    tax:         float = 0.0
    net_amount:  float = 0.0   # 實際現金流（買=負，賣=正）


def calc_slippage(price: float, direction: str, mode: Mode) -> float:
    """計算滑價後成交價"""
    if mode == Mode.IDEAL:
        return price

    slip_buy  = EXECUTION["slippage_buy"]
    slip_sell = EXECUTION["slippage_sell"]
    mult = EXECUTION["pessimistic_slippage_mult"] if mode == Mode.PESSIMISTIC else 1.0

    if direction == "buy":
        return price * (1 + slip_buy * mult)
    else:
        return price * (1 - slip_sell * mult)


def calc_commission(exec_price: float, shares: int, direction: str) -> float:
    """計算手續費"""
    amount = exec_price * shares
    if direction == "buy":
        return amount * EXECUTION["commission_buy"]
    else:
        return amount * EXECUTION["commission_sell"]


def calc_tax(exec_price: float, shares: int, direction: str) -> float:
    """計算證交稅（只有賣出有）"""
    if direction != "sell":
        return 0.0
    return exec_price * shares * EXECUTION["tax_sell"]


def apply_position_cap(shares: int, price: float, daily_volume: int,
                        mode: Mode) -> int:
    """
    部位上限：單筆不超過當日成交量的 max_volume_ratio
    ideal 模式不限制
    pessimistic 用更嚴格的 0.3%
    """
    if mode == Mode.IDEAL or daily_volume <= 0:
        return shares

    if mode == Mode.PESSIMISTIC:
        ratio = 0.003
    else:
        ratio = EXECUTION["max_volume_ratio"]

    max_shares = int(daily_volume * ratio)
    return min(shares, max_shares) if max_shares > 0 else shares


def execute_trade(trade: Trade, daily_volume: int = 0,
                  is_limit_hit: bool = False) -> Trade:
    """
    執行一筆交易，填入 exec_price / commission / tax / net_amount

    Args:
        trade: Trade 物件（raw_price 已填入）
        daily_volume: 當日成交量（計算部位上限用）
        is_limit_hit: 是否漲跌停（realistic/pessimistic 模式下無法成交）

    Returns:
        填入計算結果的 Trade（無法成交則 shares=0）
    """
    mode = Mode(trade.mode)

    # 漲跌停處理
    if is_limit_hit and mode != Mode.IDEAL:
        trade.shares = 0
        trade.exec_price = trade.raw_price
        trade.net_amount = 0.0
        return trade

    # 部位上限
    trade.shares = apply_position_cap(trade.shares, trade.raw_price,
                                       daily_volume, mode)
    if trade.shares == 0:
        trade.net_amount = 0.0
        return trade

    # 滑價
    trade.exec_price = calc_slippage(trade.raw_price, trade.direction, mode)

    # 手續費 + 稅
    trade.commission = calc_commission(trade.exec_price, trade.shares, trade.direction)
    trade.tax        = calc_tax(trade.exec_price, trade.shares, trade.direction)

    amount = trade.exec_price * trade.shares
    if trade.direction == "buy":
        trade.net_amount = -(amount + trade.commission)
    else:
        trade.net_amount = amount - trade.commission - trade.tax

    return trade
