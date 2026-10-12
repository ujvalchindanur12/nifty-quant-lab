
"""
NIFTY Quant Lab — Paper Trading Strategy Engine

Features:
- Trend and momentum signals
- CE / PE / NO TRADE decisions
- Stop-loss and target calculations
- Position sizing using rupee risk limits
- No live broker orders
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any


@dataclass
class StrategyConfig:
    max_risk_per_trade: float = 250.0
    daily_loss_limit: float = 500.0
    reward_risk_ratio: float = 2.0
    fast_ema_period: int = 9
    slow_ema_period: int = 21
    rsi_period: int = 14
    max_trades_per_day: int = 3


def _ema(values, period):
    """Calculate exponential moving average."""
    if len(values) < period:
        return None

    multiplier = 2.0 / (period + 1)
    result = sum(values[:period]) / period

    for value in values[period:]:
        result = (value * multiplier) + (
            result * (1.0 - multiplier)
        )

    return result


def _rsi(values, period=14):
    """Calculate RSI using average gains and losses."""
    if len(values) <= period:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            avg_gain * (period - 1) + gains[i]
        ) / period
        avg_loss = (
            avg_loss * (period - 1) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0

    relative_strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def calculate_signal(
    closes,
    config: Optional[StrategyConfig] = None,
) -> Dict[str, Any]:
    """
    Analyse a list of chronological NIFTY closing prices.

    closes must contain real historical candle closes,
    ordered oldest to newest.

    A list of live quotes alone is not sufficient.
    """
    config = config or StrategyConfig()
    prices = [float(value) for value in closes]

    minimum = max(
        config.slow_ema_period,
        config.rsi_period + 1,
    )

    if len(prices) < minimum:
        return {
            "signal": "NO TRADE",
            "reason": (
                f"Need at least {minimum} closing prices "
                "to calculate the indicators."
            ),
            "fast_ema": None,
            "slow_ema": None,
            "rsi": None,
        }

    if any(price <= 0 for price in prices):
        return {
            "signal": "NO TRADE",
            "reason": "Prices must all be positive.",
            "fast_ema": None,
            "slow_ema": None,
            "rsi": None,
        }

    fast = _ema(prices, config.fast_ema_period)
    slow = _ema(prices, config.slow_ema_period)
    momentum = _rsi(prices, config.rsi_period)

    if fast is None or slow is None or momentum is None:
        return {
            "signal": "NO TRADE",
            "reason": "Indicator calculation unavailable.",
            "fast_ema": fast,
            "slow_ema": slow,
            "rsi": momentum,
        }

    # Conservative thresholds to avoid extreme RSI entries.
    if fast > slow and 50 <= momentum <= 68:
        signal = "CE BIAS"
        reason = "Trend and momentum indicate bullish conditions."
    elif fast < slow and 32 <= momentum <= 50:
        signal = "PE BIAS"
        reason = "Trend and momentum indicate bearish conditions."
    else:
        signal = "NO TRADE"
        reason = "Trend and momentum do not agree sufficiently."

    return {
        "signal": signal,
        "reason": reason,
        "fast_ema": round(fast, 2),
        "slow_ema": round(slow, 2),
        "rsi": round(momentum, 2),
    }


def calculate_position(
    entry_price: float,
    stop_price: float,
    lot_size: int,
    config: Optional[StrategyConfig] = None,
    remaining_daily_loss_budget: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate a conservative paper-trade position size.

    entry_price and stop_price are option premium prices.
    lot_size is the current exchange-defined lot size.

    The estimate excludes brokerage, taxes, slippage and gaps.
    """
    config = config or StrategyConfig()

    entry = float(entry_price)
    stop = float(stop_price)
    lot = int(lot_size)

    if entry <= 0 or stop <= 0:
        raise ValueError("Entry and stop prices must be positive.")

    if stop >= entry:
        raise ValueError(
            "For a long option position, stop must be below entry."
        )

    if lot <= 0:
        raise ValueError("Lot size must be positive.")

    risk_per_unit = entry - stop
    risk_per_lot = risk_per_unit * lot

    risk_budget = config.max_risk_per_trade

    if remaining_daily_loss_budget is not None:
        daily_budget = max(
            0.0, float(remaining_daily_loss_budget)
        )
        risk_budget = min(risk_budget, daily_budget)

    lots = int(risk_budget // risk_per_lot)

    if lots < 1:
        return {
            "lots": 0,
            "quantity": 0,
            "estimated_risk": 0.0,
            "estimated_premium_cost": 0.0,
            "target_price": None,
            "status": (
                "NO TRADE: one lot exceeds the available risk budget."
            ),
        }

    quantity = lots * lot
    estimated_risk = risk_per_unit * quantity
    target = entry + (
        risk_per_unit * config.reward_risk_ratio
    )

    return {
        "lots": lots,
        "quantity": quantity,
        "estimated_risk": round(estimated_risk, 2),
        "estimated_premium_cost": round(entry * quantity, 2),
        "stop_price": round(stop, 2),
        "target_price": round(target, 2),
        "status": "PAPER TRADE CALCULATION ONLY",
    }


def check_daily_limits(
    realized_daily_pnl: float,
    trades_taken: int,
    config: Optional[StrategyConfig] = None,
) -> Dict[str, Any]:
    """Check whether the configured daily limits allow another trade."""
    config = config or StrategyConfig()
    pnl = float(realized_daily_pnl)
    trades = int(trades_taken)

    allowed = (
        pnl > -config.daily_loss_limit
        and trades < config.max_trades_per_day
    )

    if pnl <= -config.daily_loss_limit:
        reason = "Daily loss limit reached."
    elif trades >= config.max_trades_per_day:
        reason = "Maximum daily trade count reached."
    else:
        reason = "Daily limits permit evaluation."

    return {
        "allowed": allowed,
        "reason": reason,
        "realized_daily_pnl": round(pnl, 2),
        "trades_taken": trades,
        "daily_loss_limit": config.daily_loss_limit,
        "max_trades_per_day": config.max_trades_per_day,
    }


def strategy_config() -> Dict[str, Any]:
    """Return the default configuration as a dictionary."""
    return asdict(StrategyConfig())
