
import streamlit as st
import pandas as pd
import api
import strategy

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


# ==========================================
# NIFTY QUANT LAB
# PAPER TRADING AND RESEARCH ONLY
# ==========================================

st.set_page_config(
    page_title="NIFTY Quant Lab",
    page_icon="📈",
    layout="wide",
)

NIFTY_KEY = "NSE_INDEX|Nifty 50"
IST = ZoneInfo("Asia/Kolkata")

MAX_RISK_PER_TRADE = 250.0
DAILY_LOSS_LIMIT = 500.0
MAX_TRADES_PER_DAY = 3

st.title("📈 NIFTY Quant Lab")
st.caption(
    "Upstox market data | Multi-timeframe strategy research "
    "| Paper trading only"
)

st.warning(
    "PAPER MODE: This app does not place, modify, or cancel orders. "
    "Signals are experimental and are not guaranteed to be profitable."
)


# ==========================================
# SESSION STATE
# ==========================================

defaults = {
    "nifty_spot": None,
    "quote_time": None,
    "expiry_dates": [],
    "option_chain": None,
    "chain_expiry": None,
    "candles_1m": None,
    "analysis_time": None,
    "paper_pnl": 0.0,
    "paper_trades": 0,
    "paper_date": date.today().isoformat(),
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Reset today's paper statistics on a new calendar day.
if st.session_state["paper_date"] != date.today().isoformat():
    st.session_state["paper_date"] = date.today().isoformat()
    st.session_state["paper_pnl"] = 0.0
    st.session_state["paper_trades"] = 0


# ==========================================
# HELPERS
# ==========================================

def to_number(value):
    try:
        if value is None:
            return None
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except (ValueError, TypeError):
        return None


def fetch_nifty_quote():
    data = api.get_market_quote(NIFTY_KEY)

    if not isinstance(data, dict) or not data:
        raise ValueError("No NIFTY quote returned.")

    quote_data = next(iter(data.values()))
    price = to_number(quote_data.get("last_price"))

    if price is None or price <= 0:
        raise ValueError("NIFTY quote is missing or invalid.")

    return price


def candles_to_dataframe(candles):
    """
    Upstox candles commonly contain:
    timestamp, open, high, low, close, volume, open interest.
    """
    if not candles:
        raise ValueError("No historical candles returned.")

    frame = pd.DataFrame(
        candles,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "open_interest",
        ],
    )

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], errors="coerce", utc=True
    ).dt.tz_convert("Asia/Kolkata")

    for column in [
        "open", "high", "low", "close", "volume"
    ]:
        frame[column] = pd.to_numeric(
            frame[column], errors="coerce"
        )

    frame = frame.dropna(
        subset=["timestamp", "open", "high", "low", "close"]
    )

    frame = frame.sort_values("timestamp")
    frame = frame.drop_duplicates(
        subset=["timestamp"], keep="last"
    )
    frame = frame.set_index("timestamp")

    return frame


def make_completed_bars(one_minute, minutes):
    """
    Aggregate one-minute candles into completed 5m/15m bars.
    Incomplete current bars are excluded.
    """
    if one_minute is None or one_minute.empty:
        return pd.DataFrame()

    now = pd.Timestamp.now(tz="Asia/Kolkata")

    # A one-minute candle is treated as complete only after
    # its start timestamp plus one minute.
    complete_minutes = one_minute[
        one_minute.index + pd.Timedelta(minutes=1) <= now
    ].copy()

    if complete_minutes.empty:
        return pd.DataFrame()

    rule = f"{minutes}min"

    bars = complete_minutes.resample(
        rule,
        origin="start_day",
    ).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    # Exclude any bar that has not fully closed.
    bars = bars[
        bars.index + pd.Timedelta(minutes=minutes) <= now
    ]

    bars = bars.dropna(subset=["open", "high", "low", "close"])

    return bars


def basic_liquidity(row, side):
    ltp = to_number(row.get(f"{side} LTP"))
    bid = to_number(row.get(f"{side} Bid"))
    ask = to_number(row.get(f"{side} Ask"))
    volume = to_number(row.get(f"{side} Volume"))

    warnings = []

    if ltp is None or ltp <= 0:
        warnings.append("LTP missing/zero")

    if bid is None or ask is None or bid <= 0 or ask <= 0:
        warnings.append("Bid/ask missing")
    elif ask < bid:
        warnings.append("Invalid bid/ask")
    else:
        midpoint = (bid + ask) / 2
        if midpoint > 0:
            spread = (ask - bid) / midpoint * 100
            if spread > 5:
                warnings.append("Spread over 5%")

    if volume is None or volume <= 0:
        warnings.append("Volume missing/zero")

    return "; ".join(warnings) if warnings else "Passed basic checks"


# ==========================================
# 1. NIFTY QUOTE
# ==========================================

st.header("1. NIFTY Market Data")

if st.button("Refresh NIFTY 50 Quote"):
    try:
        with st.spinner("Fetching NIFTY quote..."):
            st.session_state["nifty_spot"] = fetch_nifty_quote()
            st.session_state["quote_time"] = datetime.now(
                IST
            ).strftime("%Y-%m-%d %H:%M:%S IST")

        st.success("Quote request succeeded.")

    except Exception as exc:
        st.error(f"Quote request failed: {exc}")

spot = st.session_state["nifty_spot"]

if spot is not None:
    st.metric("Last fetched NIFTY 50", f"₹{spot:,.2f}")
    st.caption(
        f"Last successful request: {st.session_state['quote_time']}. "
        "This is not a continuously refreshed quote."
    )
else:
    st.info("Refresh the quote to load the current NIFTY price.")


# ==========================================
# 2. EXPIRIES AND OPTION CHAIN
# ==========================================

st.divider()
st.header("2. NIFTY Option Chain")

if st.button("Load Available Expiry Dates"):
    try:
        with st.spinner("Loading expiries..."):
            expiries = api.get_expiry_dates(NIFTY_KEY)

        st.session_state["expiry_dates"] = expiries

        if expiries:
            st.success(f"Found {len(expiries)} future expiries.")
        else:
            st.warning("No future expiries returned.")

    except Exception as exc:
        st.error(f"Expiry request failed: {exc}")

expiries = st.session_state["expiry_dates"]

if expiries:
    selected_expiry = st.selectbox(
        "Select option expiry",
        expiries,
        key="selected_expiry",
    )

    if st.button("Fetch NIFTY Option Chain"):
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


# ==========================================
# 3. PROCESS OPTION CHAIN
# ==========================================

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
            "Strike": to_number(item.get("strike_price")),
            "Call LTP": to_number(cm.get("ltp")),
            "Call Bid": to_number(cm.get("bid_price")),
            "Call Ask": to_number(cm.get("ask_price")),
            "Call Volume": to_number(cm.get("volume")),
            "Call OI": to_number(cm.get("oi")),
            "Call IV": to_number(cg.get("iv")),
            "Put LTP": to_number(pm.get("ltp")),
            "Put Bid": to_number(pm.get("bid_price")),
            "Put Ask": to_number(pm.get("ask_price")),
            "Put Volume": to_number(pm.get("volume")),
            "Put OI": to_number(pm.get("oi")),
            "Put IV": to_number(pg.get("iv")),
        })

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["Strike"]).sort_values("Strike")

    st.caption(f"Selected expiry: {st.session_state['chain_expiry']}")

    if spot is not None and not df.empty:
        strikes = sorted(df["Strike"].dropna().unique())
        atm = min(strikes, key=lambda value: abs(value - spot))
        atm_index = strikes.index(atm)

        nearby_strikes = strikes[
            max(0, atm_index - 5):
            min(len(strikes), atm_index + 6)
        ]

        nearby = df[df["Strike"].isin(nearby_strikes)].copy()

        nearby["Call Liquidity"] = nearby.apply(
            lambda row: basic_liquidity(row, "Call"), axis=1
        )
        nearby["Put Liquidity"] = nearby.apply(
            lambda row: basic_liquidity(row, "Put"), axis=1
        )

        st.metric("Approximate ATM Strike", f"{atm:g}")
        st.dataframe(
            nearby,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download Nearby Strikes CSV",
            data=nearby.to_csv(index=False),
            file_name="nifty_nearby_strikes.csv",
            mime="text/csv",
        )

elif spot is not None:
    st.info("Load an option chain to see nearby strikes.")


# ==========================================
# 4. HISTORICAL CANDLES AND STRATEGY
# ==========================================

st.divider()
st.header("3. Multi-Timeframe Strategy Research")

st.write(
    "This research engine aggregates one-minute NIFTY candles into "
    "completed five-minute and fifteen-minute candles. It then "
    "checks EMA trend and RSI momentum on both timeframes."
)

st.info(
    "Historical candles are not a live feed. Signals may be unavailable "
    "outside the market session or if Upstox returns insufficient data."
)

lookback_days = st.selectbox(
    "Calendar days to request",
    [7, 14, 30],
    index=1,
)

if st.button("Fetch Candles and Analyse Strategy"):
    try:
        end_day = date.today()
        start_day = end_day - timedelta(days=lookback_days)

        with st.spinner("Fetching historical NIFTY candles..."):
            raw_candles = api.get_historical_candles(
                instrument_key=NIFTY_KEY,
                interval="1minute",
                from_date=start_day.isoformat(),
                to_date=end_day.isoformat(),
            )

        candle_frame = candles_to_dataframe(raw_candles)

        if candle_frame.empty:
            raise ValueError("No usable historical candles returned.")

        st.session_state["candles_1m"] = candle_frame
        st.session_state["analysis_time"] = datetime.now(
            IST
        ).strftime("%Y-%m-%d %H:%M:%S IST")

        st.success(
            f"Loaded {len(candle_frame)} one-minute candles."
        )

    except Exception as exc:
        st.error(f"Historical-candle analysis failed: {exc}")

candle_frame = st.session_state["candles_1m"]

if candle_frame is not None:
    bars5 = make_completed_bars(candle_frame, 5)
    bars15 = make_completed_bars(candle_frame, 15)

    left, right = st.columns(2)

    with left:
        st.metric("Completed 5-minute candles", len(bars5))

    with right:
        st.metric("Completed 15-minute candles", len(bars15))

    st.caption(
        f"Last analysis request: {st.session_state['analysis_time']}"
    )

    if len(bars5) < 22 or len(bars15) < 22:
        st.warning(
            "Insufficient completed candles for both timeframes. "
            "No signal will be generated until enough data is available."
        )
    else:
        config = strategy.StrategyConfig(
            max_risk_per_trade=MAX_RISK_PER_TRADE,
            daily_loss_limit=DAILY_LOSS_LIMIT,
            reward_risk_ratio=2.0,
            fast_ema_period=9,
            slow_ema_period=21,
            rsi_period=14,
            max_trades_per_day=MAX_TRADES_PER_DAY,
        )

        signal5 = strategy.calculate_signal(
            bars5["close"].tolist(), config
        )
        signal15 = strategy.calculate_signal(
            bars15["close"].tolist(), config
        )

        st.subheader("Indicator results")

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

        same_bullish = (
            signal5["signal"] == "CE BIAS"
            and signal15["signal"] == "CE BIAS"
        )
        same_bearish = (
            signal5["signal"] == "PE BIAS"
            and signal15["signal"] == "PE BIAS"
        )

        if same_bullish:
            combined = "BULLISH BIAS — PAPER RESEARCH ONLY"
            reason = "Both timeframes show a bullish indicator bias."
        elif same_bearish:
            combined = "BEARISH BIAS — PAPER RESEARCH ONLY"
            reason = "Both timeframes show a bearish indicator bias."
        else:
            combined = "NO TRADE"
            reason = (
                "Timeframes disagree or the indicators do not "
                "meet the configured conditions."
            )

        st.subheader("Combined strategy status")
        st.metric("Result", combined)
        st.write(reason)

        st.caption(
            "A CE/PE bias is not an instruction to buy an option. "
            "This experimental filter has not been validated for "
            "profitability and does not model option-premium Greeks, "
            "slippage, brokerage or taxes."
        )

        st.subheader("Recent completed 5-minute candles")
        st.dataframe(
            bars5.tail(20).reset_index(),
            use_container_width=True,
            hide_index=True,
        )


# ==========================================
# 5. PLANNED OPTION RISK CALCULATOR
# ==========================================

st.divider()
st.header("4. Paper-Trade Risk Calculator")

st.caption(
    "Calculate an estimated position size for a hypothetical long option. "
    "No order is sent to Upstox."
)

capital = st.number_input(
    "Trading capital (₹)",
    min_value=0.0,
    value=25000.0,
    step=1000.0,
)

risk_limit = st.number_input(
    "Maximum planned risk per trade (₹)",
    min_value=1.0,
    value=MAX_RISK_PER_TRADE,
    step=50.0,
)

entry = st.number_input(
    "Hypothetical option entry premium (₹)",
    min_value=0.05,
    value=100.0,
    step=1.0,
)

stop = st.number_input(
    "Hypothetical stop-loss premium (₹)",
    min_value=0.01,
    value=80.0,
    step=1.0,
)

lot_size = st.number_input(
    "Exchange lot size (verify current specification)",
    min_value=1,
    value=65,
    step=1,
)

remaining_budget = max(
    0.0,
    DAILY_LOSS_LIMIT + float(st.session_state["paper_pnl"]),
)

st.write(
    f"Paper daily P&L: ₹{st.session_state['paper_pnl']:,.2f} "
    f"| Recorded paper trades: {st.session_state['paper_trades']} "
    f"| Remaining daily risk budget: ₹{remaining_budget:,.2f}"
)

if st.button("Calculate Paper Position"):
    if stop >= entry:
        st.error(
            "For a long option, the stop premium must be below entry."
        )
    elif st.session_state["paper_trades"] >= MAX_TRADES_PER_DAY:
        st.error("Configured maximum number of daily paper trades reached.")
    elif remaining_budget <= 0:
        st.error("Daily paper loss limit has been reached.")
    else:
        try:
            config = strategy.StrategyConfig(
                max_risk_per_trade=min(
                    float(risk_limit), MAX_RISK_PER_TRADE
                ),
                daily_loss_limit=DAILY_LOSS_LIMIT,
                reward_risk_ratio=2.0,
                max_trades_per_day=MAX_TRADES_PER_DAY,
            )

            position = strategy.calculate_position(
                entry_price=entry,
                stop_price=stop,
                lot_size=int(lot_size),
                config=config,
                remaining_daily_loss_budget=remaining_budget,
            )

            lots = position.get("lots", 0)
            quantity = position.get("quantity", 0)
            cost = position.get("estimated_premium_cost", 0.0)
            risk = position.get("estimated_risk", 0.0)

            # Also constrain the estimate by the available capital.
            capital_lots = int(capital // (entry * int(lot_size)))
            allowed_lots = min(lots, capital_lots)

            if allowed_lots <= 0:
                st.warning(
                    "NO TRADE: one lot exceeds the configured risk "
                    "budget or available capital."
                )
            else:
                quantity = allowed_lots * int(lot_size)
                estimated_risk = (entry - stop) * quantity
                estimated_cost = entry * quantity
                target = entry + 2.0 * (entry - stop)

                st.metric("Lots within limits", allowed_lots)
                st.metric("Total quantity", quantity)
                st.metric("Estimated premium cost", f"₹{estimated_cost:,.2f}")
                st.metric("Estimated planned risk", f"₹{estimated_risk:,.2f}")
                st.metric("Hypothetical 2R target premium", f"₹{target:,.2f}")

                st.info(
                    "Calculation only. No position has been opened, "
                    "and no P&L has been recorded."
                )

        except Exception as exc:
            st.error(f"Risk calculation failed: {exc}")


# ==========================================
# 6. PAPER JOURNAL
# ==========================================

st.divider()
st.header("5. Paper Trading Journal")

st.write(
    "Use this section only to record a hypothetical completed trade. "
    "Enter the estimated result after your paper trade ends."
)

with st.form("paper_journal_form"):
    paper_result = st.number_input(
        "Hypothetical net P&L (₹)",
        value=0.0,
        step=50.0,
        help="Enter the paper result after estimated costs.",
    )

    submitted = st.form_submit_button("Record Paper Trade")

    if submitted:
        if st.session_state["paper_trades"] >= MAX_TRADES_PER_DAY:
            st.error("Daily paper trade limit reached.")
        elif (
            st.session_state["paper_pnl"] + paper_result
            <= -DAILY_LOSS_LIMIT
        ):
            st.session_state["paper_pnl"] += paper_result
            st.session_state["paper_trades"] += 1
            st.warning(
                "Recorded. Daily paper loss limit reached; "
                "do not record more trades today."
            )
        else:
            st.session_state["paper_pnl"] += paper_result
            st.session_state["paper_trades"] += 1
            st.success("Paper result recorded in this app session.")

st.caption(
    "The journal is session-based and is not a permanent trade ledger. "
    "It does not track broker positions or prevent actual trading."
)


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption(
    "NIFTY Quant Lab | Research and paper-trading tool. "
    "No live order execution. Historical results and indicator signals "
    "do not guarantee future returns. Actual option losses may exceed "
    "planned estimates due to gaps, slippage, charges or stop failures."
)
