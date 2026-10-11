
import streamlit as st
import pandas as pd
import requests
from datetime import date

# ==========================================
# NIFTY QUANT LAB
# Upstox market data + risk calculator
# Broker order placement is disabled.
# ==========================================

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


# ==========================================
# UPSTOX CONNECTION AND NIFTY QUOTE
# ==========================================

st.header("Upstox Connection")

if st.button("Test Upstox connection / Refresh NIFTY quote"):
    try:
        with st.spinner("Fetching NIFTY quote..."):
            data = upstox_get(
                "/market-quote/quotes",
                {"instrument_key": INDEX_KEY},
            )

        if not data:
            st.warning("Upstox returned no quote data.")
        else:
            quote = next(iter(data.values()))
            ltp = quote.get("last_price")

            if ltp is None:
                st.warning("Quote returned, but last price was missing.")
                st.json(quote)
            else:
                st.success("Quote request succeeded.")
                st.metric("NIFTY 50 quote (₹)", f"{float(ltp):,.2f}")
                st.caption(
                    "Manual refresh only. Verify quote freshness "
                    "and market status before relying on this value."
                )

    except Exception as exc:
        st.error(f"Quote request failed: {exc}")


# ==========================================
# OPTION CHAIN AND EXPIRY SELECTION
# ==========================================

st.divider()
st.header("📊 NIFTY Option Chain")
st.caption(
    "Read-only option-chain data from Upstox. "
    "No orders are placed by this section."
)

if "nifty_expiries" not in st.session_state:
    st.session_state["nifty_expiries"] = []

if st.button("Load available NIFTY expiry dates"):
    try:
        with st.spinner("Loading available expiry dates..."):
            contracts = upstox_get(
                "/option/contract",
                {"instrument_key": INDEX_KEY},
            )

        if not isinstance(contracts, list):
            st.error("Unexpected response while loading expiry dates.")
            st.json(contracts)
        else:
            today = date.today().isoformat()
            expiries = sorted({
                str(item.get("expiry"))
                for item in contracts
                if item.get("expiry")
                and str(item.get("expiry")) >= today
            })

            st.session_state["nifty_expiries"] = expiries

            if expiries:
                st.success(f"Found {len(expiries)} future expiry dates.")
            else:
                st.warning(
                    "No future expiries were returned. "
                    "Check the API response and market data access."
                )

    except Exception as exc:
        st.error(f"Could not load expiry dates: {exc}")

expiries = st.session_state["nifty_expiries"]

if expiries:
    selected_expiry = st.selectbox(
        "Select NIFTY option expiry",
        expiries,
        key="selected_nifty_expiry",
    )

    if st.button("Fetch NIFTY Option Chain"):
        try:
            with st.spinner("Fetching option-chain data..."):
                chain = upstox_get(
                    "/option/chain",
                    {
                        "instrument_key": INDEX_KEY,
                        "expiry_date": selected_expiry,
                    },
                )

            if not isinstance(chain, list) or not chain:
                st.warning(
                    "No option-chain rows returned for this expiry."
                )
            else:
                rows = []

                for item in chain:
                    call = item.get("call_options") or {}
                    put = item.get("put_options") or {}

                    call_market = call.get("market_data") or {}
                    put_market = put.get("market_data") or {}

                    call_greeks = call.get("option_greeks") or {}
                    put_greeks = put.get("option_greeks") or {}

                    rows.append({
                        "Strike": item.get("strike_price"),
                        "Call LTP": call_market.get("ltp"),
                        "Call Bid": call_market.get("bid_price"),
                        "Call Ask": call_market.get("ask_price"),
                        "Call Volume": call_market.get("volume"),
                        "Call OI": call_market.get("oi"),
                        "Call IV": call_greeks.get("iv"),
                        "Put LTP": put_market.get("ltp"),
                        "Put Bid": put_market.get("bid_price"),
                        "Put Ask": put_market.get("ask_price"),
                        "Put Volume": put_market.get("volume"),
                        "Put OI": put_market.get("oi"),
                        "Put IV": put_greeks.get("iv"),
                    })

                df_chain = pd.DataFrame(rows)

                if "Strike" in df_chain.columns:
                    df_chain = df_chain.sort_values(
                        "Strike",
                        ascending=True,
                        na_position="last",
                    )

                st.success(
                    f"Loaded {len(df_chain)} option-chain rows "
                    f"for expiry {selected_expiry}."
                )

                st.dataframe(
                    df_chain,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "Download option chain CSV",
                    data=df_chain.to_csv(index=False),
                    file_name=f"nifty_option_chain_{selected_expiry}.csv",
                    mime="text/csv",
                )

                st.caption(
                    "Verify data freshness, bid/ask spreads, and "
                    "expiry before using market data for decisions."
                )

        except Exception as exc:
            st.error(f"Option-chain request failed: {exc}")


# ==========================================
# MARKET INPUTS
# ==========================================

st.divider()
st.header("Market Inputs")

spot = st.number_input(
    "NIFTY spot price (manual input)",
    min_value=0.0,
    value=25000.0,
    step=1.0,
)

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

st.caption(
    "Manual spot input is not automatically updated by the quote button."
)


# ==========================================
# TRADE RISK CALCULATOR
# ==========================================

st.divider()
st.header("Trade Planning")

option_type = st.selectbox(
    "Option type",
    ["CE", "PE"],
)

entry_premium = st.number_input(
    "Option entry premium (₹)",
    min_value=0.05,
    value=100.0,
    step=1.0,
)

stop_premium = st.number_input(
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

if st.button("Calculate trade risk"):
    loss_per_unit = entry_premium - stop_premium

    if entry_premium <= 0:
        st.error("Entry premium must be greater than zero.")
    elif stop_premium >= entry_premium:
        st.error(
            "For a long option buy, the planned stop premium "
            "must be below the entry premium."
        )
    else:
        risk_per_unit = loss_per_unit
        risk_per_lot = risk_per_unit * lot_size

        lots_by_risk = int(max_risk // risk_per_lot)
        lots_by_capital = int(
            capital // (entry_premium * lot_size)
        )

        allowed_lots = max(
            0,
            min(lots_by_risk, lots_by_capital),
        )

        estimated_risk = allowed_lots * risk_per_lot
        estimated_cost = (
            allowed_lots * entry_premium * lot_size
        )

        st.metric("Planned risk per lot", f"₹{risk_per_lot:,.2f}")
        st.metric("Allowed lots under inputs", allowed_lots)
        st.metric("Estimated premium outlay", f"₹{estimated_cost:,.2f}")
        st.metric("Planned stop-loss amount", f"₹{estimated_risk:,.2f}")

        if allowed_lots == 0:
            st.warning(
                "No lot fits both the planned risk and capital limits."
            )

        st.caption(
            "Estimate excludes charges, slippage, gaps, and execution "
            "failures. Actual losses can exceed the planned risk."
        )


# ==========================================
# PAPER-TRADE JOURNAL
# ==========================================

st.divider()
st.header("Paper Trade Journal")
st.caption("Simulated records only. No broker orders are placed.")

if "paper_trades" not in st.session_state:
    st.session_state["paper_trades"] = []

with st.form("paper_trade_form"):
    paper_action = st.selectbox(
        "Paper action",
        ["BUY CE", "BUY PE"],
    )

    paper_entry = st.number_input(
        "Paper entry premium",
        min_value=0.0,
        value=100.0,
        step=1.0,
    )

    paper_exit = st.number_input(
        "Paper exit premium",
        min_value=0.0,
        value=105.0,
        step=1.0,
    )

    paper_quantity = st.number_input(
        "Quantity in units",
        min_value=1,
        value=1,
        step=1,
    )

    save_paper = st.form_submit_button("Save paper trade")

if save_paper:
    pnl = (paper_exit - paper_entry) * paper_quantity

    st.session_state["paper_trades"].append({
        "Date": date.today().isoformat(),
        "Action": paper_action,
        "Entry premium": paper_entry,
        "Exit premium": paper_exit,
        "Quantity": paper_quantity,
        "P&L (₹)": round(pnl, 2),
    })

    st.success("Paper trade saved in this session.")

if st.session_state["paper_trades"]:
    journal = pd.DataFrame(st.session_state["paper_trades"])

    st.dataframe(
        journal,
        use_container_width=True,
        hide_index=True,
    )

    total_pnl = journal["P&L (₹)"].sum()
    st.metric("Total paper P&L (₹)", f"{total_pnl:,.2f}")

    st.download_button(
        "Download paper journal CSV",
        data=journal.to_csv(index=False),
        file_name="nifty_paper_journal.csv",
        mime="text/csv",
    )

    if st.button("Clear paper journal"):
        st.session_state["paper_trades"] = []
        st.rerun()


# ==========================================
# FOOTER
# ==========================================

st.divider()
st.caption(
    "Educational research tool. No broker order execution is "
    "implemented. Quote freshness is not guaranteed. "
    "This app is not a continuous monitor."
)
