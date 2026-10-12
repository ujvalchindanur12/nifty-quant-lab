
import streamlit as st
import pandas as pd
import requests
import api
from datetime import date, datetime

# ==========================================
# NIFTY QUANT LAB
# READ-ONLY MARKET DATA AND RISK RESEARCH
# ==========================================

st.set_page_config(
    page_title="NIFTY Quant Lab",
    page_icon="📈",
    layout="wide",
)

BASE_URL = "https://api.upstox.com/v2"
NIFTY_KEY = "NSE_INDEX|Nifty 50"

st.title("📈 NIFTY Quant Lab")
st.caption("Upstox market data and NIFTY options research")

st.warning(
    "READ-ONLY MODE: This app does not place, modify, "
    "or cancel broker orders."
)


# ==========================================
# API HELPERS
# ==========================================

def get_access_token():
    try:
        return st.secrets.get("UPSTOX_ACCESS_TOKEN", "").strip()
    except Exception:
        return ""


def upstox_get(endpoint, params=None):
    token = get_access_token()

    if not token:
        raise ValueError(
            "UPSTOX_ACCESS_TOKEN is missing from Streamlit Secrets."
        )

    response = requests.get(
        BASE_URL + endpoint,
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
            f"{response.text[:600]}"
        )

    payload = response.json()

    if payload.get("status") == "error":
        raise RuntimeError(
            str(payload.get("errors", "Unknown Upstox API error"))[:600]
        )

    return payload.get("data")


def fetch_nifty_quote():
    data = upstox_get(
        "/market-quote/quotes",
        {"instrument_key": NIFTY_KEY},
    )

    if not isinstance(data, dict) or not data:
        raise ValueError("No NIFTY quote returned.")

    quote_data = next(iter(data.values()))
    ltp = quote_data.get("last_price")

    if ltp is None or float(ltp) <= 0:
        raise ValueError("NIFTY quote is missing or invalid.")

    return float(ltp)


def to_number(value):
    try:
        if value is None:
            return None
        result = float(value)
        if pd.isna(result):
            return None
        return result
    except (ValueError, TypeError):
        return None


# ==========================================
# SESSION STATE
# ==========================================

defaults = {
    "nifty_spot": None,
    "quote_time": None,
    "expiry_dates": [],
    "option_chain": None,
    "chain_expiry": None,
}

for key, default in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ==========================================
# 1. NIFTY QUOTE
# ==========================================

st.header("1. Upstox Connection")

if st.button("Refresh NIFTY 50 Quote"):
    try:
        with st.spinner("Fetching NIFTY quote..."):
            spot = fetch_nifty_quote()

        st.session_state["nifty_spot"] = spot
        st.session_state["quote_time"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        st.success("NIFTY quote request succeeded.")

    except Exception as exc:
        st.error(f"Quote request failed: {exc}")

if st.session_state["nifty_spot"] is not None:
    st.metric(
        "Last fetched NIFTY 50",
        f"₹{st.session_state['nifty_spot']:,.2f}",
    )
    st.caption(
        f"Last successful request: {st.session_state['quote_time']}. "
        "Refresh manually to request a new quote."
    )
else:
    st.info("Tap Refresh NIFTY 50 Quote to load market data.")


# ==========================================
# 2. OPTION EXPIRIES
# ==========================================

st.divider()
st.header("2. NIFTY Option Chain")
st.caption("Read-only market data; no orders are placed.")

if st.button("Load Available Expiry Dates"):
    try:
        with st.spinner("Loading NIFTY expiries..."):
            contracts = upstox_get(
                "/option/contract",
                {"instrument_key": NIFTY_KEY},
            )

        if not isinstance(contracts, list):
            raise ValueError("Unexpected option-contract response.")

        today = date.today().isoformat()

        expiries = sorted({
            str(item["expiry"])
            for item in contracts
            if item.get("expiry")
            and str(item["expiry"]) >= today
        })

        st.session_state["expiry_dates"] = expiries

        if expiries:
            st.success(f"Found {len(expiries)} expiry dates.")
        else:
            st.warning("No future expiry dates returned.")

    except Exception as exc:
        st.error(f"Expiry request failed: {exc}")

expiries = st.session_state["expiry_dates"]

if expiries:
    selected_expiry = st.selectbox(
        "Select NIFTY option expiry",
        expiries,
        key="selected_expiry",
    )

    if st.button("Fetch NIFTY Option Chain"):
        try:
            with st.spinner("Fetching option-chain data..."):
                chain = upstox_get(
                    "/option/chain",
                    {
                        "instrument_key": NIFTY_KEY,
                        "expiry_date": selected_expiry,
                    },
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

    st.caption(f"Expiry: {st.session_state['chain_expiry']}")

    st.subheader("ATM and Nearby Strikes")

    if st.session_state["nifty_spot"] is not None:
        spot = float(st.session_state["nifty_spot"])
        st.write(f"Using last fetched NIFTY quote: ₹{spot:,.2f}")
    else:
        spot = st.number_input(
            "Manual NIFTY spot",
            min_value=1.0,
            value=25000.0,
            step=50.0,
        )
        st.warning("ATM uses manual spot until a quote is fetched.")

    strikes = sorted(df["Strike"].dropna().unique())

    if strikes:
        atm = min(strikes, key=lambda value: abs(value - spot))
        atm_index = strikes.index(atm)

        nearby_strikes = strikes[
            max(0, atm_index - 5):
            min(len(strikes), atm_index + 6)
        ]

        nearby = df[df["Strike"].isin(nearby_strikes)].copy()

        st.metric("Approximate ATM Strike", f"{atm:g}")

        def check_liquidity(row, side):
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

            return "; ".join(warnings) if warnings else "No basic warning"

        nearby["Call Liquidity"] = nearby.apply(
            lambda row: check_liquidity(row, "Call"), axis=1
        )
        nearby["Put Liquidity"] = nearby.apply(
            lambda row: check_liquidity(row, "Put"), axis=1
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


# ==========================================
# 4. QUOTE QUALITY RESEARCH
# ==========================================

st.divider()
st.header("3. ATM Quote Quality")

st.info(
    "Quote quality is not a directional trading signal. "
    "This section does not recommend buying a CE or PE."
)

if df.empty:
    st.warning("Load an option chain first.")
elif st.session_state["nifty_spot"] is None:
    st.warning("Refresh NIFTY quote before checking ATM quotes.")
else:
    spot = float(st.session_state["nifty_spot"])
    atm_idx = (df["Strike"] - spot).abs().idxmin()
    atm_row = df.loc[atm_idx]

    st.write(f"ATM reference strike: {atm_row['Strike']:g}")

    def calculate_spread(row, side):
        bid = to_number(row.get(f"{side} Bid"))
        ask = to_number(row.get(f"{side} Ask"))

        if (
            bid is None or ask is None
            or bid <= 0 or ask <= 0 or ask < bid
        ):
            return None

        midpoint = (bid + ask) / 2

        if midpoint <= 0:
            return None

        return (ask - bid) / midpoint * 100

    call_ltp = to_number(atm_row.get("Call LTP"))
    put_ltp = to_number(atm_row.get("Put LTP"))

    call_spread = calculate_spread(atm_row, "Call")
    put_spread = calculate_spread(atm_row, "Put")

    st.write(
        "Call LTP: "
        + (f"₹{call_ltp:.2f}" if call_ltp is not None else "Unavailable")
    )
    st.write(
        "Put LTP: "
        + (f"₹{put_ltp:.2f}" if put_ltp is not None else "Unavailable")
    )
    st.write(
        "Call spread: "
        + (f"{call_spread:.2f}%" if call_spread is not None else "Unavailable")
    )
    st.write(
        "Put spread: "
        + (f"{put_spread:.2f}%" if put_spread is not None else "Unavailable")
    )

    if (
        call_spread is not None
        and put_spread is not None
        and call_spread <= 5
        and put_spread <= 5
    ):
        st.success("Both ATM spreads passed the basic 5% filter.")
    else:
        st.warning("NO TRADE: ATM quotes failed basic spread checks.")

    st.caption(
        "A passing spread filter does not establish an expected profit "
        "or guarantee that an order can be executed at the displayed price."
    )


# ==========================================
# 5. PLANNED RISK CALCULATOR
# ==========================================

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
    "Lot size (verify current exchange specification)",
    min_value=1,
    value=65,
    step=1,
)

if st.button("Calculate Planned Risk"):
    if stop >= entry:
        st.error("For a long option, stop premium must be below entry.")
    else:
        risk_per_lot = (entry - stop) * lot_size
        cost_per_lot = entry * lot_size

        lots_by_risk = int(risk_limit // risk_per_lot)
        lots_by_capital = int(capital // cost_per_lot)
        allowed_lots = max(0, min(lots_by_risk, lots_by_capital))

        st.metric("Planned risk per lot", f"₹{risk_per_lot:,.2f}")
        st.metric("Premium cost per lot", f"₹{cost_per_lot:,.2f}")
        st.metric("Lots within inputs", allowed_lots)
        st.metric(
            "Total planned risk",
            f"₹{allowed_lots * risk_per_lot:,.2f}",
        )

        if allowed_lots == 0:
            st.warning("No lot fits both the risk and capital limits.")

        st.caption(
            "This is only an estimate. Charges, slippage, gaps, and "
            "stop execution failures can increase actual losses. "
            "The calculator does not control broker orders."
        )


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption(
    "Research dashboard only. No live broker order execution is "
    "implemented. Data may be delayed, stale, or unavailable. "
    "This app is not a continuous monitor."
)
