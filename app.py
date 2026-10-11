
import streamlit as st
import pandas as pd
import requests
from datetime import date, datetime

# =====================================================
# NIFTY QUANT LAB
# Upstox market data, signal research and risk calculator
# LIVE ORDER EXECUTION IS NOT IMPLEMENTED
# =====================================================

st.set_page_config(
    page_title="NIFTY Quant Lab",
    page_icon="📈",
    layout="wide",
)

API_BASE = "https://api.upstox.com/v2"
INDEX_KEY = "NSE_INDEX|Nifty 50"

st.title("📈 NIFTY Quant Lab")
st.caption("NIFTY options research and risk dashboard")

st.warning(
    "READ-ONLY MODE: No live broker orders are placed, "
    "modified, or cancelled by this application."
)


# =====================================================
# API HELPERS
# =====================================================

def get_token():
    return st.secrets.get("UPSTOX_ACCESS_TOKEN", "").strip()


def upstox_get(endpoint, params=None):
    token = get_token()

    if not token:
        raise ValueError(
            "UPSTOX_ACCESS_TOKEN is missing from Streamlit Secrets."
        )

    response = requests.get(
        f"{API_BASE}{endpoint}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        params=params or {},
        timeout=20,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Upstox HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    payload = response.json()

    if payload.get("status") == "error":
        raise RuntimeError(str(payload.get("errors", payload))[:800])

    return payload.get("data")


def get_spot():
    data = upstox_get(
        "/market-quote/quotes",
        {"instrument_key": INDEX_KEY},
    )

    if not isinstance(data, dict) or not data:
        raise ValueError("No NIFTY quote returned.")

    quote = next(iter(data.values()))
    price = quote.get("last_price")

    if price is None or float(price) <= 0:
        raise ValueError("NIFTY quote has no valid last price.")

    return float(price)


def number(value):
    try:
        result = float(value)
        if pd.notna(result):
            return result
    except (TypeError, ValueError):
        pass
    return None


# =====================================================
# SESSION STATE
# =====================================================

defaults = {
    "spot": None,
    "spot_time": None,
    "expiries": [],
    "chain": None,
    "chain_expiry": None,
    "paper_journal": [],
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# =====================================================
# NIFTY QUOTE
# =====================================================

st.header("1. Upstox Connection")

if st.button("Refresh NIFTY 50 Quote"):
    try:
        with st.spinner("Requesting NIFTY quote..."):
            st.session_state["spot"] = get_spot()
            st.session_state["spot_time"] = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        st.success("NIFTY quote request succeeded.")

    except Exception as exc:
        st.error(f"Quote request failed: {exc}")

if st.session_state["spot"] is not None:
    st.metric(
        "Last fetched NIFTY 50",
        f"{st.session_state['spot']:,.2f}",
    )
    st.caption(
        f"Last successful request: {st.session_state['spot_time']}. "
        "This is not continuously updated."
    )
else:
    st.info("Refresh the quote to load the current available value.")


# =====================================================
# OPTION CHAIN
# =====================================================

st.divider()
st.header("2. NIFTY Option Chain")
st.caption("Market-data display only. No orders are placed.")

if st.button("Load Available Expiry Dates"):
    try:
        with st.spinner("Loading expiry dates..."):
            contracts = upstox_get(
                "/option/contract",
                {"instrument_key": INDEX_KEY},
            )

        if not isinstance(contracts, list):
            st.error("Unexpected expiry response from Upstox.")
        else:
            today = date.today().isoformat()
            expiries = sorted({
                str(item["expiry"])
                for item in contracts
                if item.get("expiry")
                and str(item["expiry"]) >= today
            })

            st.session_state["expiries"] = expiries

            if expiries:
                st.success(f"Found {len(expiries)} expiry dates.")
            else:
                st.warning("No future expiry dates returned.")

    except Exception as exc:
        st.error(f"Expiry request failed: {exc}")

expiries = st.session_state["expiries"]

if expiries:
    expiry = st.selectbox(
        "Select NIFTY expiry",
        expiries,
        key="expiry_choice",
    )

    if st.button("Fetch Option Chain"):
        try:
            with st.spinner("Fetching option chain..."):
                chain = upstox_get(
                    "/option/chain",
                    {
                        "instrument_key": INDEX_KEY,
                        "expiry_date": expiry,
                    },
                )

            if isinstance(chain, list) and chain:
                st.session_state["chain"] = chain
                st.session_state["chain_expiry"] = expiry
                st.success(f"Received {len(chain)} strike rows.")
            else:
                st.session_state["chain"] = None
                st.warning("No option-chain rows returned.")

        except Exception as exc:
            st.error(f"Option-chain request failed: {exc}")

chain = st.session_state["chain"]
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

    df = pd.DataFrame(rows)
    df = df.dropna(subset=["Strike"]).sort_values("Strike")

    st.caption(f"Expiry loaded: {st.session_state['chain_expiry']}")

    st.subheader("ATM and Nearby Strikes")

    if st.session_state["spot"] is not None:
        spot = float(st.session_state["spot"])
        st.write(f"Using last fetched spot: {spot:,.2f}")
    else:
        spot = st.number_input(
            "Manual NIFTY spot (used only until a quote is fetched)",
            min_value=1.0,
            value=25000.0,
            step=50.0,
        )
        st.warning("ATM selection currently uses manual spot input.")

    strikes = sorted(df["Strike"].dropna().unique())

    if strikes:
        atm = min(strikes, key=lambda x: abs(x - spot))
        atm_idx = strikes.index(atm)
        nearby_strikes = strikes[
            max(0, atm_idx - 5): min(len(strikes), atm_idx + 6)
        ]

        nearby = df[df["Strike"].isin(nearby_strikes)].copy()

        st.metric("Approximate ATM Strike", f"{atm:g}")

        # -------------------------------------------------
        # Liquidity warnings
        # -------------------------------------------------

        def liquidity_check(row, side):
            ltp = number(row.get(f"{side} LTP"))
            bid = number(row.get(f"{side} Bid"))
            ask = number(row.get(f"{side} Ask"))
            volume = number(row.get(f"{side} Volume"))

            warnings = []

            if ltp is None or ltp <= 0:
                warnings.append("LTP missing/zero")

            if bid is None or ask is None or bid <= 0 or ask <= 0:
                warnings.append("Bid/ask missing")
            elif ask < bid:
                warnings.append("Invalid bid/ask")
            else:
                mid = (bid + ask) / 2
                if mid > 0 and ((ask - bid) / mid) > 0.05:
                    warnings.append("Spread over 5%")

            if volume is None or volume <= 0:
                warnings.append("Volume missing/zero")

            return "; ".join(warnings) if warnings else "No basic warning"

        nearby["Call Liquidity"] = nearby.apply(
            lambda row: liquidity_check(row, "Call"), axis=1
        )
        nearby["Put Liquidity"] = nearby.apply(
            lambda row: liquidity_check(row, "Put"), axis=1
        )

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


# =====================================================
# RULE-BASED SIGNAL RESEARCH
# =====================================================

st.divider()
st.header("3. Rule-Based Signal Research")

st.info(
    "This section evaluates a single option-chain snapshot. "
    "It does not establish a trend or predict future returns. "
    "It cannot issue a reliable BUY signal from one snapshot alone."
)

if not chain or df.empty:
    st.warning(
        "Load an option chain first to run the basic quote-quality checks."
    )
else:
    if st.session_state["spot"] is None:
        st.warning(
            "Refresh the NIFTY quote before interpreting the chain."
        )

    spot_value = st.session_state["spot"]

    if spot_value is not None:
        atm_row = df.iloc[
            (df["Strike"] - spot_value).abs().argsort()[:1]
        ].iloc[0]

        st.write(f"ATM reference strike: {atm_row['Strike']:g}")

        call_ltp = number(atm_row.get("Call LTP"))
        call_bid = number(atm_row.get("Call Bid"))
        call_ask = number(atm_row.get("Call Ask"))

        put_ltp = number(atm_row.get("Put LTP"))
        put_bid = number(atm_row.get("Put Bid"))
        put_ask = number(atm_row.get("Put Ask"))

        call_valid = (
            call_ltp is not None and call_ltp > 0
            and call_bid is not None and call_bid > 0
            and call_ask is not None and call_ask >= call_bid
        )

        put_valid = (
            put_ltp is not None and put_ltp > 0
            and put_bid is not None and put_bid > 0
            and put_ask is not None and put_ask >= put_bid
        )

        if call_valid and put_valid:
            call_mid = (call_bid + call_ask) / 2
            put_mid = (put_bid + put_ask) / 2

            call_spread_pct = (
                (call_ask - call_bid) / call_mid * 100
                if call_mid > 0 else 999
            )
            put_spread_pct = (
                (put_ask - put_bid) / put_mid * 100
                if put_mid > 0 else 999
            )

            st.write(f"ATM Call LTP: ₹{call_ltp:.2f}")
            st.write(f"ATM Put LTP: ₹{put_ltp:.2f}")
            st.write(f"Call spread: {call_spread_pct:.2f}%")
            st.write(f"Put spread: {put_spread_pct:.2f}%")

            if call_spread_pct <= 5 and put_spread_pct <= 5:
                st.success(
                    "Basic ATM quote checks passed. "
                    "This is not a buy/sell recommendation."
                )
            else:
                st.warning(
                    "One or both ATM spreads exceed 5%. "
                    "Treat this snapshot as unsuitable for a signal."
                )
        else:
            st.warning(
                "ATM call or put has missing/invalid quotes. "
                "Signal status: NO TRADE."
            )

    st.caption(
        "No directional entry signal is produced here. A single "
        "snapshot is insufficient to establish momentum, trend, "
        "or a statistically tested strategy."
    )


# =====================================================
# RISK CALCULATOR
# =====================================================

st.divider()
st.header("4. Planned Risk Calculator")

capital = st.number_input(
    "Trading capital (₹)",
    min_value=0.0,
    value=25000.0,
    step=1000.0,
)

risk_limit = st.number_input(
    "Maximum planned risk per trade (₹)",
    min_value=1.0,
    value=500.0,
    step=50.0,
)

option_type = st.selectbox("Option type", ["CE", "PE"])

entry = st.number_input(
    "Planned entry premium (₹)",
    min_value=0.05,
    value=100.0,
    step=1.0,
)

stop = st.number_input(
    "Planned stop-loss premium (₹)",
    min_value=0.0,
    value=80.0,
    step=1.0,
)

lot_size = st.number_input(
    "Lot size — verify current exchange specification",
    min_value=1,
    value=65,
    step=1,
)

if st.button("Calculate Planned Risk"):
    if stop >= entry:
        st.error("Stop-loss premium must be below entry for a long option.")
    else:
        per_unit_risk = entry - stop
        per_lot_risk = per_unit_risk * lot_size
        per_lot_cost = entry * lot_size

        lots_risk = int(risk_limit // per_lot_risk)
        lots_capital = int(capital // per_lot_cost)
        allowed_lots = max(0, min(lots_risk, lots_capital))

        st.metric("Planned risk per lot", f"₹{per_lot_risk:,.2f}")
        st.metric("Premium outlay per lot", f"₹{per_lot_cost:,.2f}")
        st.metric("Lots within inputs", allowed_lots)
        st.metric(
            "Total planned risk",
            f"₹{allowed_lots * per_lot_risk:,.2f}",
        )

        if allowed_lots == 0:
            st.warning("No lot fits both the risk and capital limits.")

        st.caption(
            "This is an estimate only. Charges, slippage, gaps, and "
            "failed stop execution can increase actual losses."
        )


# =====================================================
# OPTIONAL PAPER JOURNAL
# =====================================================

st.divider()
st.header("5. Optional Paper Journal")
st.caption("Simulated records only; no broker orders are sent.")

if "paper_journal" not in st.session_state:
    st.session_state["paper_journal"] = []

with st.form("paper_journal_form"):
    action = st.selectbox("Action", ["BUY CE", "BUY PE"])
    paper_entry = st.number_input(
        "Entry premium", min_value=0.0, value=100.0
    )
    paper_exit = st.number_input(
        "Exit premium", min_value=0.0, value=105.0
    )
    quantity = st.number_input(
        "Quantity in units", min_value=1, value=1
    )
    save = st.form_submit_button("Save Journal Entry")

if save:
    pnl = (paper_exit - paper_entry) * quantity
    st.session_state["paper_journal"].append({
        "Date": date.today().isoformat(),
        "Action": action,
        "Entry": paper_entry,
        "Exit": paper_exit,
        "Quantity": quantity,
        "P&L": round(pnl, 2),
    })
    st.success("Journal entry saved for this session.")

if st.session_state["paper_journal"]:
    journal = pd.DataFrame(st.session_state["paper_journal"])
    st.dataframe(journal, use_container_width=True, hide_index=True)

    st.metric("Journal P&L (₹)", f"{journal['P&L'].sum():,.2f}")

    st.download_button(
        "Download Journal CSV",
        data=journal.to_csv(index=False),
        file_name="nifty_journal.csv",
        mime="text/csv",
    )


# =====================================================
# FOOTER
# =====================================================

st.divider()
st.caption(
    "Research tool only. No live order execution is implemented. "
    "Quotes may be delayed, stale, or unavailable. "
    "This app is not a continuous monitor."
)
