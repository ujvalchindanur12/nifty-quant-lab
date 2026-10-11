
import streamlit as st
import pandas as pd
import requests
from datetime import date

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
    "READ-ONLY MODE: This app does not place, modify, "
    "or cancel live broker orders."
)


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
            f"{response.text[:1000]}"
        )

    result = response.json()
    if result.get("status") == "error":
        raise RuntimeError(str(result.get("errors", result))[:1000])

    return result.get("data")


def get_spot():
    data = upstox_get(
        "/market-quote/quotes",
        {"instrument_key": INDEX_KEY},
    )

    if not isinstance(data, dict) or not data:
        raise ValueError("No NIFTY quote was returned.")

    quote = next(iter(data.values()))
    price = quote.get("last_price")

    if price is None or float(price) <= 0:
        raise ValueError("NIFTY quote has no valid last price.")

    return float(price)


# ==========================================
# LIVE NIFTY QUOTE
# ==========================================

st.header("Upstox Connection")

if "nifty_spot" not in st.session_state:
    st.session_state["nifty_spot"] = None

if st.button("Refresh NIFTY 50 quote"):
    try:
        with st.spinner("Fetching quote..."):
            st.session_state["nifty_spot"] = get_spot()

        st.success("NIFTY quote refreshed.")
    except Exception as exc:
        st.error(f"Quote request failed: {exc}")

if st.session_state["nifty_spot"] is not None:
    st.metric(
        "Last fetched NIFTY 50 value",
        f"₹{st.session_state['nifty_spot']:,.2f}",
    )
    st.caption(
        "This is the last successfully fetched quote, not a "
        "continuously updated price. Refresh to request a new quote."
    )
else:
    st.info("Refresh the quote before using automatic ATM selection.")


# ==========================================
# OPTION CHAIN
# ==========================================

st.divider()
st.header("📊 NIFTY Option Chain")
st.caption("Read-only data. No orders are placed.")

if "nifty_expiries" not in st.session_state:
    st.session_state["nifty_expiries"] = []

if "nifty_chain" not in st.session_state:
    st.session_state["nifty_chain"] = None

if "nifty_chain_expiry" not in st.session_state:
    st.session_state["nifty_chain_expiry"] = None

if st.button("Load available NIFTY expiry dates"):
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
            st.session_state["nifty_expiries"] = expiries

            if expiries:
                st.success(f"Found {len(expiries)} future expiries.")
            else:
                st.warning("No future expiry dates returned.")

    except Exception as exc:
        st.error(f"Expiry request failed: {exc}")

expiries = st.session_state["nifty_expiries"]

if expiries:
    expiry = st.selectbox(
        "Select NIFTY expiry",
        expiries,
        key="nifty_expiry_select",
    )

    if st.button("Fetch NIFTY Option Chain"):
        try:
            with st.spinner("Fetching option-chain data..."):
                chain = upstox_get(
                    "/option/chain",
                    {
                        "instrument_key": INDEX_KEY,
                        "expiry_date": expiry,
                    },
                )

            if not isinstance(chain, list) or not chain:
                st.warning("No option-chain rows returned.")
                st.session_state["nifty_chain"] = None
            else:
                st.session_state["nifty_chain"] = chain
                st.session_state["nifty_chain_expiry"] = expiry
                st.success(f"Loaded {len(chain)} strikes.")

        except Exception as exc:
            st.error(f"Option-chain request failed: {exc}")

chain = st.session_state["nifty_chain"]

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
            "Strike": item.get("strike_price"),
            "Call LTP": cm.get("ltp"),
            "Call Bid": cm.get("bid_price"),
            "Call Ask": cm.get("ask_price"),
            "Call Volume": cm.get("volume"),
            "Call OI": cm.get("oi"),
            "Call IV": cg.get("iv"),
            "Put LTP": pm.get("ltp"),
            "Put Bid": pm.get("bid_price"),
            "Put Ask": pm.get("ask_price"),
            "Put Volume": pm.get("volume"),
            "Put OI": pm.get("oi"),
            "Put IV": pg.get("iv"),
        })

    df = pd.DataFrame(rows)
    df["Strike"] = pd.to_numeric(df["Strike"], errors="coerce")
    df = df.dropna(subset=["Strike"]).sort_values("Strike")

    # Use last fetched quote if available; otherwise ask for manual spot.
    st.subheader("ATM and nearby strikes")

    if st.session_state["nifty_spot"] is not None:
        spot = float(st.session_state["nifty_spot"])
        st.write(f"Using last fetched NIFTY value: ₹{spot:,.2f}")
    else:
        spot = st.number_input(
            "Enter NIFTY spot manually",
            min_value=1.0,
            value=25000.0,
            step=50.0,
        )
        st.warning(
            "ATM is based on your manual input until you refresh "
            "the NIFTY quote."
        )

    strikes = sorted(df["Strike"].dropna().unique())

    if strikes:
        atm = min(strikes, key=lambda strike: abs(strike - spot))
        atm_index = strikes.index(atm)
        lower = max(0, atm_index - 5)
        upper = min(len(strikes), atm_index + 6)
        nearby = strikes[lower:upper]

        st.metric("Approximate ATM strike", f"{atm:g}")
        st.caption(
            "Showing ATM and up to five listed strikes on each side."
        )

        nearby_df = df[df["Strike"].isin(nearby)].copy()

        # Liquidity checks for both calls and puts.
        for side in ["Call", "Put"]:
            ltp = pd.to_numeric(
                nearby_df[f"{side} LTP"], errors="coerce"
            )
            bid = pd.to_numeric(
                nearby_df[f"{side} Bid"], errors="coerce"
            )
            ask = pd.to_numeric(
                nearby_df[f"{side} Ask"], errors="coerce"
            )
            volume = pd.to_numeric(
                nearby_df[f"{side} Volume"], errors="coerce"
            )

            spread = ask - bid
            midpoint = (ask + bid) / 2
            spread_pct = (spread / midpoint) * 100

            warnings = []
            for i in nearby_df.index:
                reasons = []

                if pd.isna(ltp.loc[i]) or ltp.loc[i] <= 0:
                    reasons.append("LTP missing/zero")

                if (
                    pd.isna(bid.loc[i])
                    or pd.isna(ask.loc[i])
                    or bid.loc[i] <= 0
                    or ask.loc[i] <= 0
                ):
                    reasons.append("Bid/ask missing")
                elif ask.loc[i] < bid.loc[i]:
                    reasons.append("Invalid bid/ask")
                elif (
                    pd.notna(spread_pct.loc[i])
                    and spread_pct.loc[i] > 5
                ):
                    reasons.append("Spread over 5%")

                if pd.isna(volume.loc[i]) or volume.loc[i] <= 0:
                    reasons.append("Zero/missing volume")

                warnings.append(
                    "; ".join(reasons) if reasons else "Review quote"
                )

            nearby_df[f"{side} Liquidity Check"] = warnings

        st.dataframe(
            nearby_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download filtered option chain CSV",
            data=nearby_df.to_csv(index=False),
            file_name="nifty_nearby_option_chain.csv",
            mime="text/csv",
        )

        st.caption(
            "A warning is a screening flag, not proof that a contract "
            "is untradeable. Even contracts without warnings require "
            "fresh quotes and manual verification."
        )


# ==========================================
# RISK CALCULATOR
# ==========================================

st.divider()
st.header("Trade Risk Calculator")

capital = st.number_input(
    "Trading capital (₹)",
    min_value=0.0,
    value=25000.0,
    step=1000.0,
)

max_risk = st.number_input(
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

if st.button("Calculate risk and allowed lots"):
    if stop >= entry:
        st.error(
            "For a long option, the planned stop premium must be "
            "below the entry premium."
        )
    else:
        risk_per_unit = entry - stop
        risk_per_lot = risk_per_unit * lot_size
        cost_per_lot = entry * lot_size

        lots_by_risk = int(max_risk // risk_per_lot)
        lots_by_capital = int(capital // cost_per_lot)
        allowed_lots = max(
            0, min(lots_by_risk, lots_by_capital)
        )

        st.metric("Planned loss per lot", f"₹{risk_per_lot:,.2f}")
        st.metric("Premium cost per lot", f"₹{cost_per_lot:,.2f}")
        st.metric("Allowed lots under inputs", allowed_lots)
        st.metric(
            "Planned stop-loss amount",
            f"₹{allowed_lots * risk_per_lot:,.2f}",
        )

        if allowed_lots == 0:
            st.warning(
                "No lot fits both the capital and planned-risk limits."
            )

        st.caption(
            "This is a planning estimate, not an order control. It "
            "excludes charges and slippage. Actual loss can exceed "
            "planned risk, especially during gaps or execution failures."
        )


# ==========================================
# PAPER JOURNAL (OPTIONAL, SESSION ONLY)
# ==========================================

st.divider()
st.header("Paper Trade Journal")
st.caption("Optional simulated journal; no broker orders are sent.")

if "paper_trades" not in st.session_state:
    st.session_state["paper_trades"] = []

with st.form("paper_trade_form"):
    action = st.selectbox("Paper action", ["BUY CE", "BUY PE"])
    paper_entry = st.number_input(
        "Paper entry premium", min_value=0.0, value=100.0
    )
    paper_exit = st.number_input(
        "Paper exit premium", min_value=0.0, value=105.0
    )
    quantity = st.number_input(
        "Quantity in units", min_value=1, value=1
    )
    save = st.form_submit_button("Save paper trade")

if save:
    st.session_state["paper_trades"].append({
        "Date": date.today().isoformat(),
        "Action": action,
        "Entry": paper_entry,
        "Exit": paper_exit,
        "Quantity": quantity,
        "P&L": round((paper_exit - paper_entry) * quantity, 2),
    })
    st.success("Paper trade saved in this session.")

if st.session_state["paper_trades"]:
    journal = pd.DataFrame(st.session_state["paper_trades"])
    st.dataframe(journal, use_container_width=True, hide_index=True)
    st.metric("Paper P&L (₹)", f"{journal['P&L'].sum():,.2f}")

    st.download_button(
        "Download paper journal CSV",
        data=journal.to_csv(index=False),
        file_name="nifty_paper_journal.csv",
        mime="text/csv",
    )


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption(
    "Research dashboard only. No broker order execution is "
    "implemented. Data may be delayed, unavailable, or stale. "
    "This app is not a continuous monitor."
)
