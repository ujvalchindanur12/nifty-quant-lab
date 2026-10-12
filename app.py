
import streamlit as st
import pandas as pd
import api
import strategy

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


# =========================================================
# NIFTY QUANT LAB — MANUAL TRADING RESEARCH
# NO AUTOMATED ORDER PLACEMENT
# =========================================================

st.set_page_config(
    page_title="NIFTY Quant Lab",
    page_icon="📈",
    layout="wide",
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
IST = ZoneInfo("Asia/Kolkata")

CAPITAL_DEFAULT = 25000.0
RISK_DEFAULT = 500.0
DAILY_LOSS_LIMIT = 1000.0

st.title("📈 NIFTY Quant Lab")
st.caption("NIFTY options research • Manual execution only")

st.warning(
    "RESEARCH MODE: This app never places orders. "
    "Signals are experimental and are not guaranteed to be profitable."
)


# =========================================================
# SESSION STATE
# =========================================================

defaults = {
    "nifty_spot": None,
    "quote_time": None,
    "expiry_dates": [],
    "option_chain": None,
    "chain_expiry": None,
    "candles": None,
    "analysis_time": None,
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default


# =========================================================
# HELPERS
# =========================================================

def number(value):
    try:
        if value is None:
            return None
        result = float(value)
        if pd.isna(result):
            return None
        return result
    except (ValueError, TypeError):
        return None


def get_quote():
    data = api.get_market_quote(NIFTY_KEY)

    if not isinstance(data, dict) or not data:
        raise ValueError("No NIFTY quote returned.")

    item = next(iter(data.values()))
    price = number(item.get("last_price"))

    if price is None or price <= 0:
        raise ValueError("Invalid NIFTY quote.")

    return price


def candle_frame(candles):
    if not candles:
        raise ValueError("No historical candles returned.")

    columns = [
        "timestamp", "open", "high", "low",
        "close", "volume", "open_interest",
    ]

    frame = pd.DataFrame(candles, columns=columns)

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Kolkata")

    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame = frame.dropna(
        subset=["timestamp", "open", "high", "low", "close"]
    )

    frame = frame.sort_values("timestamp")
    frame = frame.drop_duplicates("timestamp", keep="last")
    return frame.set_index("timestamp")


def aggregate_bars(frame, minutes):
    """Aggregate one-minute candles and exclude incomplete bars."""
    if frame is None or frame.empty:
        return pd.DataFrame()

    now = pd.Timestamp.now(tz="Asia/Kolkata")

    complete = frame[
        frame.index + pd.Timedelta(minutes=1) <= now
    ].copy()

    if complete.empty:
        return pd.DataFrame()

    bars = complete.resample(
        f"{minutes}min",
        origin="start_day",
    ).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    bars = bars[
        bars.index + pd.Timedelta(minutes=minutes) <= now
    ]

    return bars.dropna(
        subset=["open", "high", "low", "close"]
    )


def spread_percent(bid, ask):
    bid = number(bid)
    ask = number(ask)

    if (
        bid is None or ask is None
        or bid <= 0 or ask <= 0 or ask < bid
    ):
        return None

    midpoint = (bid + ask) / 2

    if midpoint <= 0:
        return None

    return 100 * (ask - bid) / midpoint


def liquidity_status(row, side):
    ltp = number(row.get(f"{side} LTP"))
    bid = number(row.get(f"{side} Bid"))
    ask = number(row.get(f"{side} Ask"))
    volume = number(row.get(f"{side} Volume"))
    spread = spread_percent(bid, ask)

    problems = []

    if ltp is None or ltp <= 0:
        problems.append("Missing LTP")

    if spread is None:
        problems.append("Invalid bid/ask")
    elif spread > 5:
        problems.append("Spread above 5%")

    if volume is None or volume <= 0:
        problems.append("No reported volume")

    return (
        "CHECK: " + ", ".join(problems)
        if problems else "Basic checks passed"
    )


# =========================================================
# 1. LIVE QUOTE
# =========================================================

st.header("1. NIFTY Market Data")

if st.button("Refresh NIFTY Quote"):
    try:
        with st.spinner("Requesting NIFTY quote..."):
            st.session_state["nifty_spot"] = get_quote()
            st.session_state["quote_time"] = datetime.now(
                IST
            ).strftime("%Y-%m-%d %H:%M:%S IST")

        st.success("Quote refreshed.")

    except Exception as exc:
        st.error(f"Quote request failed: {exc}")

spot = st.session_state["nifty_spot"]

if spot is not None:
    st.metric("Last fetched NIFTY 50", f"₹{spot:,.2f}")
    st.caption(
        f"Quote time: {st.session_state['quote_time']}. "
        "Refresh manually; this is not a continuous live feed."
    )
else:
    st.info("Refresh the NIFTY quote to begin.")


# =========================================================
# 2. OPTION EXPIRIES AND CHAIN
# =========================================================

st.divider()
st.header("2. Option Chain")

if st.button("Load Expiry Dates"):
    try:
        with st.spinner("Loading expiry dates..."):
            st.session_state["expiry_dates"] = api.get_expiry_dates(
                NIFTY_KEY
            )

        if st.session_state["expiry_dates"]:
            st.success(
                f"Loaded {len(st.session_state['expiry_dates'])} expiries."
            )
        else:
            st.warning("No future expiries returned.")

    except Exception as exc:
        st.error(f"Expiry request failed: {exc}")

expiries = st.session_state["expiry_dates"]

if expiries:
    selected_expiry = st.selectbox(
        "Select expiry",
        expiries,
        key="selected_expiry",
    )

    if st.button("Fetch Option Chain"):
        try:
            with st.spinner("Fetching option chain..."):
                chain = api.get_option_chain(
                    NIFTY_KEY, selected_expiry
                )

            if not isinstance(chain, list) or not chain:
                st.session_state["option_chain"] = None
                st.warning("No option-chain rows returned.")
            else:
                st.session_state["option_chain"] = chain
                st.session_state["chain_expiry"] = selected_expiry
                st.success(f"Loaded {len(chain)} strike rows.")

        except Exception as exc:
            st.error(f"Option-chain request failed: {exc}")

chain = st.session_state["option_chain"]
df = pd.DataFrame()

if chain:
    rows = []

    for item in chain:
        call = item.get("call_options") or {}
        put = item.get("put_options") or {}

        cm = call.get("market_data") or {}
        pm = put.get("market_data") or {}

        cg = call.get("option_greeks") or {}
        pg = put.get("option_greeks") or {}

        rows.append({
            "Strike": number(item.get("strike_price")),
            "Call LTP": number(cm.get("ltp")),
            "Call Bid": number(cm.get("bid_price")),
            "Call Ask": number(cm.get("ask_price")),
            "Call Volume": number(cm.get("volume")),
            "Call OI": number(cm.get("oi")),
            "Call IV": number(cg.get("iv")),
            "Put LTP": number(pm.get("ltp")),
            "Put Bid": number(pm.get("bid_price")),
            "Put Ask": number(pm.get("ask_price")),
            "Put Volume": number(pm.get("volume")),
            "Put OI": number(pm.get("oi")),
            "Put IV": number(pg.get("iv")),
        })

    df = pd.DataFrame(rows).dropna(subset=["Strike"])
    df = df.sort_values("Strike")

    st.caption(f"Expiry: {st.session_state['chain_expiry']}")

    if spot is not None and not df.empty:
        strikes = sorted(df["Strike"].unique())
        atm = min(strikes, key=lambda x: abs(x - spot))
        atm_index = strikes.index(atm)
        nearby_strikes = strikes[
            max(0, atm_index - 5): min(len(strikes), atm_index + 6)
        ]

        nearby = df[df["Strike"].isin(nearby_strikes)].copy()

        nearby["Call Liquidity"] = nearby.apply(
            lambda row: liquidity_status(row, "Call"), axis=1
        )
        nearby["Put Liquidity"] = nearby.apply(
            lambda row: liquidity_status(row, "Put"), axis=1
        )

        st.metric("Approximate ATM Strike", f"{atm:g}")
        st.dataframe(
            nearby,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download Option Chain CSV",
            data=nearby.to_csv(index=False),
            file_name="nifty_nearby_strikes.csv",
            mime="text/csv",
        )


# =========================================================
# 3. MULTI-TIMEFRAME SIGNAL ANALYSIS
# =========================================================

st.divider()
st.header("3. Strategy Signal")

st.write(
    "Entry research uses completed 5-minute candles and confirmation "
    "uses completed 15-minute candles. The indicators are experimental."
)

lookback_days = st.selectbox(
    "Historical data lookback",
    [7, 14, 30],
    index=1,
)

if st.button("Fetch Candles and Analyse"):
    try:
        end_day = date.today()
        start_day = end_day - timedelta(days=lookback_days)

        with st.spinner("Fetching historical candles..."):
            candles = api.get_historical_candles(
                instrument_key=NIFTY_KEY,
                interval="1minute",
                from_date=start_day.isoformat(),
                to_date=end_day.isoformat(),
            )

        frame = candle_frame(candles)

        if frame.empty:
            raise ValueError("No usable candles returned.")

        st.session_state["candles"] = frame
        st.session_state["analysis_time"] = datetime.now(
            IST
        ).strftime("%Y-%m-%d %H:%M:%S IST")

        st.success(f"Loaded {len(frame)} one-minute candles.")

    except Exception as exc:
        st.error(f"Analysis request failed: {exc}")

frame = st.session_state["candles"]

combined_signal = "NO TRADE"
combined_reason = "Fetch and validate historical candles first."
signal5 = None
signal15 = None

if frame is not None:
    bars5 = aggregate_bars(frame, 5)
    bars15 = aggregate_bars(frame, 15)

    col1, col2 = st.columns(2)
    col1.metric("Completed 5-minute bars", len(bars5))
    col2.metric("Completed 15-minute bars", len(bars15))

    st.caption(
        f"Analysis requested: {st.session_state['analysis_time']}"
    )

    # Require enough bars for the 21-period EMA and RSI.
    if len(bars5) < 30 or len(bars15) < 30:
        combined_reason = "Insufficient completed candles."
        st.warning(
            "Insufficient candle history. No signal will be generated."
        )
    else:
        config = strategy.StrategyConfig(
            max_risk_per_trade=RISK_DEFAULT,
            daily_loss_limit=DAILY_LOSS_LIMIT,
            reward_risk_ratio=2.0,
            fast_ema_period=9,
            slow_ema_period=21,
            rsi_period=14,
            max_trades_per_day=3,
        )

        signal5 = strategy.calculate_signal(
            bars5["close"].tolist(), config
        )
        signal15 = strategy.calculate_signal(
            bars15["close"].tolist(), config
        )

        st.subheader("Indicator confirmation")

        results = pd.DataFrame([
            {
                "Timeframe": "5-minute entry",
                "Bias": signal5["signal"],
                "EMA 9": signal5["fast_ema"],
                "EMA 21": signal5["slow_ema"],
                "RSI": signal5["rsi"],
                "Reason": signal5["reason"],
            },
            {
                "Timeframe": "15-minute confirmation",
                "Bias": signal15["signal"],
                "EMA 9": signal15["fast_ema"],
                "EMA 21": signal15["slow_ema"],
                "RSI": signal15["rsi"],
                "Reason": signal15["reason"],
            },
        ])

        st.dataframe(
            results,
            use_container_width=True,
            hide_index=True,
        )

        if (
            signal5["signal"] == "CE BIAS"
            and signal15["signal"] == "CE BIAS"
        ):
            combined_signal = "CE BIAS"
            combined_reason = (
                "Both timeframes show a bullish indicator bias. "
                "This is not a verified buy signal."
            )

        elif (
            signal5["signal"] == "PE BIAS"
            and signal15["signal"] == "PE BIAS"
        ):
            combined_signal = "PE BIAS"
            combined_reason = (
                "Both timeframes show a bearish indicator bias. "
                "This is not a verified buy signal."
            )

        else:
            combined_signal = "NO TRADE"
            combined_reason = (
                "Timeframes disagree or the entry conditions are not met."
            )

st.subheader("Combined result")
st.metric("Strategy status", combined_signal)
st.write(combined_reason)

if frame is not None:
    st.subheader("Recent completed 5-minute candles")
    st.dataframe(
        bars5.tail(20).reset_index(),
        use_container_width=True,
        hide_index=True,
    )


# =========================================================
# 4. OPTION LIQUIDITY AND PREMIUM REFERENCE
# =========================================================

st.divider()
st.header("4. Option Reference")

if df.empty or spot is None:
    st.info("Refresh the quote and fetch the option chain first.")
else:
    strikes = sorted(df["Strike"].unique())
    atm = min(strikes, key=lambda x: abs(x - spot))
    atm_row = df.loc[
        (df["Strike"] - atm).abs().idxmin()
    ]

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("ATM Call")
        st.write(f"Strike: {atm:g}")
        st.write(f"LTP: ₹{atm_row['Call LTP']}" if pd.notna(
            atm_row["Call LTP"]
        ) else "LTP unavailable")

        call_spread = spread_percent(
            atm_row["Call Bid"], atm_row["Call Ask"]
        )

        st.write(
            f"Bid/ask spread: {call_spread:.2f}%"
            if call_spread is not None
            else "Bid/ask spread unavailable"
        )
        st.write(
            liquidity_status(atm_row, "Call")
        )

    with c2:
        st.subheader("ATM Put")
        st.write(f"Strike: {atm:g}")
        st.write(f"LTP: ₹{atm_row['Put LTP']}" if pd.notna(
            atm_row["Put LTP"]
        ) else "LTP unavailable")

        put_spread = spread_percent(
            atm_row["Put Bid"], atm_row["Put Ask"]
        )

        st.write(
            f"Bid/ask spread: {put_spread:.2f}%"
            if put_spread is not None
            else "Bid/ask spread unavailable"
        )
        st.write(
            liquidity_status(atm_row, "Put")
        )

    st.caption(
        "These are ATM references, not necessarily the best contract. "
        "Option-chain quotes may be stale. Verify the chosen contract "
        "and price in your broker app before deciding."
    )


# =========================================================
# 5. MANUAL TRADE RISK CALCULATOR
# =========================================================

st.divider()
st.header("5. Manual Options Risk Calculator")

st.write(
    "Enter a proposed long-option trade. This estimates risk and "
    "position size; it does not place an order."
)

capital = st.number_input(
    "Available capital (₹)",
    min_value=0.0,
    value=CAPITAL_DEFAULT,
    step=1000.0,
)

risk_limit = st.number_input(
    "Maximum planned risk per trade (₹)",
    min_value=1.0,
    max_value=RISK_DEFAULT,
    value=RISK_DEFAULT,
    step=50.0,
)

option_side = st.selectbox(
    "Option side",
    ["CE", "PE"],
)

proposed_strike = st.number_input(
    "Proposed strike",
    min_value=1.0,
    value=float(
        min(df["Strike"], key=lambda x: abs(x - spot))
        if spot is not None and not df.empty
        else 25000.0
    ),
    step=50.0,
)

entry = st.number_input(
    "Proposed entry premium (₹)",
    min_value=0.05,
    value=100.0,
    step=1.0,
)

stop = st.number_input(
    "Stop-loss premium (₹)",
    min_value=0.01,
    value=80.0,
    step=1.0,
)

lot_size = st.number_input(
    "Current exchange lot size — verify before use",
    min_value=1,
    value=65,
    step=1,
)

if st.button("Calculate Position and Risk"):
    if stop >= entry:
        st.error("For a long option, stop-loss must be below entry.")
    else:
        risk_per_lot = (entry - stop) * int(lot_size)
        cost_per_lot = entry * int(lot_size)

        if risk_per_lot <= 0 or cost_per_lot <= 0:
            st.error("Invalid position inputs.")
        else:
            lots_by_risk = int(risk_limit // risk_per_lot)
            lots_by_capital = int(capital // cost_per_lot)
            lots = min(lots_by_risk, lots_by_capital)

            if lots < 1:
                st.error(
                    "NO TRADE: one lot exceeds the selected risk "
                    "limit or available capital."
                )
            else:
                quantity = lots * int(lot_size)
                premium_cost = entry * quantity
                planned_risk = (entry - stop) * quantity
                target = entry + 2 * (entry - stop)

                st.metric("Lots within limits", lots)
                st.metric("Total quantity", quantity)
                st.metric(
                    "Estimated premium cost",
                    f"₹{premium_cost:,.2f}",
                )
                st.metric(
                    "Estimated planned risk",
                    f"₹{planned_risk:,.2f}",
                )
                st.metric(
                    "Illustrative 2R target premium",
                    f"₹{target:,.2f}",
                )

                st.warning(
                    "This is a mathematical estimate, not an order "
                    "recommendation. Actual losses can exceed planned "
                    "risk because of gaps, slippage, charges, or failed "
                    "stop execution. Verify current lot size and contract "
                    "details with your broker."
                )


# =========================================================
# FOOTER
# =========================================================

st.divider()
st.caption(
    "NIFTY Quant Lab — research dashboard for manual decision-making. "
    "No live order placement. Indicators are experimental and "
    "have not been proven profitable. Never trade solely from a signal."
)
