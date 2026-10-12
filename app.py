import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import api
import strategy

# NIFTY Quant Lab — manual decision support only.
# This app NEVER places orders. Verify every value in your broker app before buying.

st.set_page_config(page_title="NIFTY Quant Lab", page_icon="📈", layout="wide")
IST = ZoneInfo("Asia/Kolkata")
NIFTY_KEY = "NSE_INDEX|Nifty 50"
CAPITAL_DEFAULT = 25000.0
MAX_RISK_DEFAULT = 500.0
MAX_DAILY_LOSS_DEFAULT = 1000.0

st.title("📈 NIFTY Quant Lab")
st.caption("Manual trading decision support • No automatic order placement")

st.warning(
    "Important: this is an experimental indicator, not a proven profitable strategy. "
    "A green status is a checklist result, not a guarantee. Confirm the contract, live premium, "
    "spread and order details in Upstox/Angel One before placing any manual order."
)

def safe_float(value, default=np.nan):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def get_quote_price(payload):
    """Handle common Upstox market-quote response shapes."""
    if not isinstance(payload, dict):
        return np.nan
    data = payload.get("data", payload)
    if isinstance(data, dict):
        for key, item in data.items():
            if isinstance(item, dict):
                for field in ("last_price", "ltp", "close_price"):
                    val = safe_float(item.get(field))
                    if np.isfinite(val):
                        return val
        for field in ("last_price", "ltp", "close_price"):
            val = safe_float(data.get(field))
            if np.isfinite(val):
                return val
    return np.nan

def normalize_candles(payload):
    if isinstance(payload, pd.DataFrame):
        df = payload.copy()
    else:
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        candles = data.get("candles", []) if isinstance(data, dict) else data
        if not candles:
            return pd.DataFrame()
        # Upstox candle format: [timestamp, open, high, low, close, volume, oi]
        df = pd.DataFrame(candles)
        if df.shape[1] >= 6:
            df = df.iloc[:, :6]
            df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
        elif df.shape[1] >= 5:
            df = df.iloc[:, :5]
            df.columns = ["timestamp", "open", "high", "low", "close"]
    if df.empty:
        return df
    # Support either named columns or positional columns.
    lower = {str(c).lower(): c for c in df.columns}
    required = ["timestamp", "open", "high", "low", "close"]
    if not all(x in lower for x in required):
        return pd.DataFrame()
    df = df.rename(columns={lower[k]: k for k in lower})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert(IST)
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" not in df:
        df["volume"] = 0
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    return df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

def aggregate_bars(df, minutes):
    if df.empty:
        return pd.DataFrame()
    x = df.copy().set_index("timestamp")
    rule = f"{minutes}min"
    out = x.resample(rule, origin="start_day", offset="15min", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open", "high", "low", "close"]).reset_index()
    # Remove the currently forming candle, and candles outside today's session for signal use.
    now = datetime.now(IST)
    out = out[out["timestamp"] + timedelta(minutes=minutes) <= now]
    out = out[
        (out["timestamp"].dt.time >= datetime.strptime("09:15", "%H:%M").time())
        & (out["timestamp"].dt.time < datetime.strptime("15:30", "%H:%M").time())
    ]
    return out.reset_index(drop=True)

def parse_chain_rows(chain_payload):
    """Convert common Upstox option-chain response into rows."""
    if not isinstance(chain_payload, dict):
        return []
    data = chain_payload.get("data", chain_payload)
    if isinstance(data, dict):
        # Some responses wrap rows in 'data'; others return list there.
        rows = data.get("chain") or data.get("option_chain") or data.get("data")
        if rows is None and all(isinstance(v, dict) for v in data.values()):
            rows = list(data.values())
    else:
        rows = data
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        strike = safe_float(row.get("strike_price", row.get("strike")))
        if not np.isfinite(strike):
            continue
        item = {"strike": strike}
        for side, aliases in [
            ("CE", ("call_options", "ce", "call")),
            ("PE", ("put_options", "pe", "put")),
        ]:
            opt = next((row.get(k) for k in aliases if isinstance(row.get(k), dict)), {})
            market = opt.get("market_data", opt.get("marketData", {})) if isinstance(opt, dict) else {}
            item[side + "_key"] = opt.get("instrument_key") or opt.get("instrumentKey")
            item[side + "_ltp"] = safe_float(market.get("ltp", market.get("last_price")))
            item[side + "_bid"] = safe_float(market.get("bid_price", market.get("bidPrice")))
            item[side + "_ask"] = safe_float(market.get("ask_price", market.get("askPrice")))
            item[side + "_volume"] = safe_float(market.get("volume"), 0)
            item[side + "_oi"] = safe_float(market.get("oi", market.get("open_interest")), 0)
        result.append(item)
    return result

def spread_pct(bid, ask):
    if not np.isfinite(bid) or not np.isfinite(ask) or bid <= 0 or ask <= 0:
        return np.nan
    mid = (bid + ask) / 2
    return ((ask - bid) / mid) * 100 if mid > 0 else np.nan

def call_strategy(closes, cfg):
    try:
        result = strategy.calculate_signal(closes, cfg)
        if isinstance(result, dict):
            return str(result.get("bias", result.get("signal", result.get("status", "NO TRADE")))).upper()
        if hasattr(result, "bias"):
            return str(result.bias).upper()
        return str(result).upper()
    except Exception:
        return "NO TRADE"

def canonical_bias(value):
    s = str(value).upper()
    if "CE" in s and "NO TRADE" not in s:
        return "CE BIAS"
    if "PE" in s and "NO TRADE" not in s:
        return "PE BIAS"
    return "NO TRADE"

with st.sidebar:
    st.header("Risk settings")
    capital = st.number_input("Available capital (₹)", min_value=1000.0, value=CAPITAL_DEFAULT, step=1000.0)
    risk_per_trade = st.number_input("Maximum planned risk per trade (₹)", min_value=50.0, max_value=500.0, value=MAX_RISK_DEFAULT, step=50.0)
    daily_loss_limit = st.number_input("Daily loss limit (₹)", min_value=100.0, max_value=2500.0, value=MAX_DAILY_LOSS_DEFAULT, step=100.0)
    lot_size = st.number_input("NIFTY lot size — verify with broker", min_value=1, value=65, step=1)
    st.caption("Do not assume the lot size is current. Verify it with your broker.")

if "spot" not in st.session_state:
    st.session_state.spot = np.nan
if "expiry_dates" not in st.session_state:
    st.session_state.expiry_dates = []
if "chain_rows" not in st.session_state:
    st.session_state.chain_rows = []
if "chain_expiry" not in st.session_state:
    st.session_state.chain_expiry = None
if "candles" not in st.session_state:
    st.session_state.candles = pd.DataFrame()
if "analysis" not in st.session_state:
    st.session_state.analysis = None

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("1. Refresh NIFTY quote", use_container_width=True):
        try:
            q = api.get_market_quote([NIFTY_KEY])
            price = get_quote_price(q)
            if np.isfinite(price):
                st.session_state.spot = price
                st.session_state.quote_time = datetime.now(IST)
                st.success(f"NIFTY quote fetched: {price:.2f}")
            else:
                st.error("Could not read NIFTY price from the API response. Check the API token and quote endpoint.")
        except Exception as e:
            st.error(f"NIFTY quote failed: {e}")

with c2:
    if st.button("2. Load expiry dates", use_container_width=True):
        try:
            response = api.get_expiry_dates(instrument_key=NIFTY_KEY, include_expired=False)
            data = response.get("data", response) if isinstance(response, dict) else response
            dates = []
            if isinstance(data, list):
                for x in data:
                    if isinstance(x, str):
                        dates.append(x)
                    elif isinstance(x, dict):
                        val = x.get("expiry") or x.get("expiry_date") or x.get("date")
                        if val:
                            dates.append(str(val)[:10])
            elif isinstance(data, dict):
                dates = [str(v)[:10] for v in data.get("expiry_dates", [])]
            st.session_state.expiry_dates = sorted(set(dates))
            if not st.session_state.expiry_dates:
                st.warning("Expiry dates were returned in an unexpected format. Check api.py response handling.")
            else:
                st.success(f"Loaded {len(st.session_state.expiry_dates)} expiry date(s).")
        except Exception as e:
            st.error(f"Expiry lookup failed: {e}")

with c3:
    if st.button("3. Fetch candles & analyse", use_container_width=True):
        try:
            end = date.today()
            start = end - timedelta(days=14)
            raw = api.get_historical_candles(
                instrument_key=NIFTY_KEY,
                interval="1minute",
                to_date=end.isoformat(),
                from_date=start.isoformat(),
            )
            df = normalize_candles(raw)
            st.session_state.candles = df
            if df.empty:
                st.session_state.analysis = None
                st.error("No usable candle data returned.")
            else:
                bars5 = aggregate_bars(df, 5)
                bars15 = aggregate_bars(df, 15)
                cfg = strategy.StrategyConfig(
                    risk_per_trade=risk_per_trade,
                    daily_loss_limit=daily_loss_limit,
                    reward_risk=2.0,
                    ema_fast=9,
                    ema_slow=21,
                    rsi_period=14,
                    max_trades_per_day=3,
                )
                s5 = canonical_bias(call_strategy(bars5["close"].tolist(), cfg)) if len(bars5) >= 30 else "NO TRADE"
                s15 = canonical_bias(call_strategy(bars15["close"].tolist(), cfg)) if len(bars15) >= 30 else "NO TRADE"
                combined = s5 if s5 == s15 and s5 != "NO TRADE" else "NO TRADE"
                last_ts = bars5["timestamp"].max() if not bars5.empty else pd.NaT
                now = datetime.now(IST)
                fresh = False
                if pd.notna(last_ts):
                    age = (now - last_ts.to_pydatetime()).total_seconds() / 60
                    fresh = age <= 15 and now.time() >= datetime.strptime("09:15", "%H:%M").time() and now.time() <= datetime.strptime("15:30", "%H:%M").time()
                st.session_state.analysis = {
                    "5m": s5, "15m": s15, "combined": combined,
                    "last_candle": last_ts, "fresh": fresh,
                    "bars5": bars5, "bars15": bars15,
                    "analysis_time": now,
                }
                st.success(f"Analysis complete. 5m: {s5} | 15m: {s15} | Combined: {combined}")
        except Exception as e:
            st.session_state.analysis = None
            st.error(f"Analysis failed: {e}")

if np.isfinite(st.session_state.spot):
    st.metric("Latest NIFTY quote", f"{st.session_state.spot:,.2f}",
              help="Refresh the quote during market hours. Confirm it against your broker.")
    qt = st.session_state.get("quote_time")
    if qt:
        st.caption("Quote fetched at " + qt.strftime("%d %b %Y, %I:%M:%S %p IST"))
else:
    st.info("Tap **1. Refresh NIFTY quote** to fetch the latest available index quote.")

st.subheader("Strategy confirmation")
if st.session_state.analysis:
    a = st.session_state.analysis
    m1, m2, m3 = st.columns(3)
    m1.metric("5-minute entry", a["5m"])
    m2.metric("15-minute confirmation", a["15m"])
    m3.metric("Combined result", a["combined"])
    if pd.notna(a["last_candle"]):
        st.write("Last completed 5-minute candle:", a["last_candle"].strftime("%d %b %Y, %I:%M %p %Z"))
    if not a["fresh"]:
        st.error("STALE / OUT-OF-SESSION DATA: no trade candidate will be approved. Refresh during regular market hours.")
    elif a["combined"] == "NO TRADE":
        st.warning("NO TRADE: the two timeframes do not agree or entry conditions are not met. Do not force an entry.")
    else:
        st.info("Directional bias is aligned. The option candidate still must pass live quote, liquidity, premium and risk checks.")
else:
    st.info("Fetch candles and analyse to calculate the 5-minute and 15-minute signals.")

st.subheader("Option expiry and chain")
expiry = None
if st.session_state.expiry_dates:
    expiry = st.selectbox("Choose expiry", st.session_state.expiry_dates)
    if st.button("4. Fetch selected option chain", use_container_width=True):
        try:
            payload = api.get_option_chain(instrument_key=NIFTY_KEY, expiry_date=expiry)
            st.session_state.chain_rows = parse_chain_rows(payload)
            st.session_state.chain_expiry = expiry
            if st.session_state.chain_rows:
                st.success(f"Loaded {len(st.session_state.chain_rows)} strike rows for {expiry}.")
            else:
                st.error("Option chain returned, but this app could not interpret its format. Do not use a candidate until this is fixed.")
        except Exception as e:
            st.error(f"Option chain failed: {e}")
else:
    st.caption("Load expiry dates first.")

# Clear, conservative candidate logic.
st.subheader("Manual trade decision")
if not st.session_state.analysis:
    st.warning("WAIT — run strategy analysis first.")
elif not st.session_state.analysis["fresh"]:
    st.error("DO NOT BUY FROM THIS DASHBOARD: candle data is stale or outside regular market hours.")
elif st.session_state.analysis["combined"] == "NO TRADE":
    st.error("NO TRADE — the strategy has not confirmed a direction.")
elif not np.isfinite(st.session_state.spot):
    st.warning("WAIT — refresh the NIFTY quote before selecting a contract.")
elif not st.session_state.chain_rows or not st.session_state.chain_expiry:
    st.warning("WAIT — load the option chain for the selected expiry.")
else:
    rows = pd.DataFrame(st.session_state.chain_rows)
    if rows.empty:
        st.warning("WAIT — no option strikes were parsed.")
    else:
        spot = float(st.session_state.spot)
        rows["distance"] = (rows["strike"] - spot).abs()
        nearest = rows.sort_values("distance").iloc[0]
        direction = st.session_state.analysis["combined"]
        side = "CE" if direction == "CE BIAS" else "PE"
        strike = float(nearest["strike"])
        key = nearest.get(side + "_key")
        premium = safe_float(nearest.get(side + "_ltp"))
        bid = safe_float(nearest.get(side + "_bid"))
        ask = safe_float(nearest.get(side + "_ask"))
        volume = safe_float(nearest.get(side + "_volume"), 0)
        spread = spread_pct(bid, ask)
        st.write(f"Nearest-to-ATM candidate: **NIFTY {strike:.0f} {side}**, expiry **{st.session_state.chain_expiry}**")
        st.caption("ATM is only a starting candidate; it is not automatically the best option to buy.")
        if np.isfinite(premium) and premium > 0:
            # Conservative illustrative premium stop: 25% below entry; 2R target.
            entry = ask if np.isfinite(ask) and ask > 0 else premium
            stop = round(entry * 0.75, 2)
            target = round(entry + 2 * (entry - stop), 2)
            risk_per_unit = entry - stop
            max_units_by_risk = int(risk_per_trade // risk_per_unit) if risk_per_unit > 0 else 0
            max_lots = max_units_by_risk // int(lot_size)
            lots_by_capital = int(capital // (entry * int(lot_size)))
            lots = max(0, min(max_lots, lots_by_capital))
            quantity = lots * int(lot_size)
            estimated_cost = quantity * entry
            estimated_risk = quantity * risk_per_unit
            checks = {
                "Correct contract key present": isinstance(key, str) and bool(key),
                "Option quote appears live": np.isfinite(premium) and premium > 0,
                "Bid and ask available": np.isfinite(bid) and np.isfinite(ask) and bid > 0 and ask > 0 and ask >= bid,
                "Bid/ask spread <= 2%": np.isfinite(spread) and spread <= 2.0,
                "Some traded volume": volume > 0,
                "Risk-based quantity is at least one lot": lots >= 1,
            }
            st.markdown("#### Candidate levels (calculated, not guaranteed)")
            a1, a2, a3 = st.columns(3)
            a1.metric("Buy-limit reference (ask)", f"₹{entry:.2f}")
            a2.metric("Illustrative stop-loss", f"₹{stop:.2f}")
            a3.metric("Illustrative target (2R)", f"₹{target:.2f}")
            b1, b2, b3 = st.columns(3)
            b1.metric("Lots", str(lots))
            b2.metric("Quantity", str(quantity))
            b3.metric("Estimated risk", f"₹{estimated_risk:,.0f}")
            st.caption(f"Estimated premium outlay: ₹{estimated_cost:,.0f}. Excludes charges, slippage and gap risk. Lot size entered: {int(lot_size)}.")
            st.markdown("#### Buy checklist")
            for label, ok in checks.items():
                st.write(("✅ " if ok else "❌ ") + label)
            all_ok = all(checks.values()) and st.session_state.analysis["fresh"] and direction in ("CE BIAS", "PE BIAS")
            if all_ok:
                st.success(
                    f"CHECKLIST PASSED — candidate is NIFTY {strike:.0f} {side} ({st.session_state.chain_expiry}). "
                    f"Reference premium ₹{entry:.2f}; illustrative stop ₹{stop:.2f}; target ₹{target:.2f}. "
                    "This is not a guaranteed buy signal. Recheck the live quote and levels in your broker app before manually placing any order."
                )
            else:
                st.error("NOT APPROVED — at least one quote, liquidity or risk check failed. Do not buy from this result.")
        else:
            st.error("No valid option premium was returned for the candidate. Do not trade until the option-chain data is fixed.")

st.subheader("Recent completed 5-minute candles")
if st.session_state.analysis and not st.session_state.analysis["bars5"].empty:
    st.dataframe(st.session_state.analysis["bars5"].tail(10).sort_values("timestamp", ascending=False), use_container_width=True)
elif not st.session_state.candles.empty:
    st.caption("Raw candles loaded, but no valid completed 5-minute bars were available in the current session.")

st.divider()
st.caption(
    "Risk note: the stop/target shown here are mechanical examples based on the option premium, not validated support/resistance. "
    "Options can gap through stops and lose most or all of their value. This app does not send orders and does not establish profitability."
)
