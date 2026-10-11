
import streamlit as st
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(
    page_title="NIFTY Quant Lab",
    page_icon="📈",
    layout="wide"
)

st.title("📈 NIFTY Quant Lab")
st.caption("NIFTY options research and risk dashboard")

st.warning(
    "READ-ONLY MODE: This app does not place, modify, "
    "or cancel live broker orders."
)

# --------------------------------------------------
# UPSTOX READ-ONLY QUOTE
# --------------------------------------------------

st.subheader("Upstox Connection")


def get_upstox_quote():
    """Fetch a read-only NIFTY 50 quote."""

    token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")

    if not token:
        return None, (
            "Access token is missing. Check Streamlit Secrets."
        )

    url = "https://api.upstox.com/v2/market-quote/quotes"

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    params = {
        "instrument_key": "NSE_INDEX|Nifty 50"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return None, (
                f"Upstox returned HTTP {response.status_code}. "
                "Check whether your access token is valid."
            )

        payload = response.json()
        data = payload.get("data", {})

        if not data:
            return None, "Upstox returned no quote data."

        quote = next(iter(data.values()), None)

        if not isinstance(quote, dict):
            return None, "Unexpected quote response format."

        last_price = quote.get("last_price")

        if last_price is None:
            return None, "The quote has no last_price field."

        return float(last_price), None

    except requests.Timeout:
        return None, "Upstox request timed out. Try again."

    except requests.RequestException:
        return None, (
            "Unable to connect to Upstox. Check your internet."
        )

    except (ValueError, TypeError):
        return None, (
            "Upstox returned data that could not be processed."
        )


if st.button("Test Upstox connection / Refresh NIFTY quote"):
    with st.spinner("Checking Upstox..."):
        quote, error = get_upstox_quote()

    if error:
        st.error(error)
    else:
        st.success("Quote request succeeded.")
        st.metric("NIFTY 50 quote (₹)", f"{quote:,.2f}")
        st.caption(
            "Manual refresh only. Check market status and "
            "quote freshness before relying on the price."
        )

st.divider()

# --------------------------------------------------
# MARKET INPUTS
# --------------------------------------------------

st.subheader("Market Inputs")

col1, col2 = st.columns(2)

with col1:
    nifty = st.number_input(
        "NIFTY spot price (manual input)",
        min_value=0.0,
        value=25000.0,
        step=50.0
    )

with col2:
    capital = st.number_input(
        "Trading capital (₹)",
        min_value=0,
        value=25000,
        step=1000
    )

# --------------------------------------------------
# RISK CONTROLS
# --------------------------------------------------

st.subheader("Risk Controls")

risk_pct = st.slider(
    "Maximum planned risk per trade (%)",
    min_value=0.5,
    max_value=2.0,
    value=1.0,
    step=0.5
)

risk_amount = capital * risk_pct / 100

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Planned risk budget",
        f"₹{risk_amount:,.0f}"
    )

with col2:
    st.metric(
        "Manual NIFTY level",
        f"{nifty:,.2f}"
    )

# --------------------------------------------------
# TRADE RISK CALCULATOR
# --------------------------------------------------

st.subheader("Trade Planning")

option_type = st.selectbox(
    "Option type",
    ["CE", "PE"]
)

premium = st.number_input(
    "Option entry premium (₹)",
    min_value=0.0,
    value=100.0,
    step=1.0
)

stop_premium = st.number_input(
    "Planned stop-loss premium (₹)",
    min_value=0.0,
    value=80.0,
    step=1.0
)

lot_size = st.number_input(
    "Lot size (verify current exchange specification)",
    min_value=1,
    value=65,
    step=1
)

if st.button("Calculate trade risk"):
    if premium <= stop_premium:
        st.error(
            "Entry premium must be greater than stop-loss premium."
        )
    else:
        loss_per_unit = premium - stop_premium
        loss_per_lot = loss_per_unit * lot_size
        max_lots = int(risk_amount // loss_per_lot)

        st.metric(
            "Estimated loss per lot",
            f"₹{loss_per_lot:,.2f}"
        )

        st.metric("Lots within risk budget", max_lots)

        if max_lots == 0:
            st.warning(
                "One lot exceeds your planned risk budget."
            )
        else:
            st.info(
                "Planning calculation only. Charges, slippage, "
                "and gap risk are excluded."
            )

# --------------------------------------------------
# PAPER-TRADE JOURNAL
# --------------------------------------------------

st.subheader("Paper-Trade Journal")

if "trades" not in st.session_state:
    st.session_state.trades = []

with st.form("paper_trade_form"):
    symbol = st.text_input("Instrument", "NIFTY")

    side = st.selectbox(
        "Position",
        ["BUY CE", "BUY PE"]
    )

    entry = st.number_input(
        "Paper entry premium",
        min_value=0.0,
        value=100.0
    )

    exit_price = st.number_input(
        "Paper exit premium",
        min_value=0.0,
        value=105.0
    )

    quantity = st.number_input(
        "Quantity in units",
        min_value=1,
        value=1
    )

    submitted = st.form_submit_button("Save paper trade")

    if submitted:
        pnl = (exit_price - entry) * quantity

        st.session_state.trades.append({
            "Time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "Instrument": symbol,
            "Position": side,
            "Entry": entry,
            "Exit": exit_price,
            "Quantity": quantity,
            "Paper P&L": round(pnl, 2)
        })

        st.success("Paper trade saved for this session.")

if st.session_state.trades:
    df = pd.DataFrame(st.session_state.trades)

    st.dataframe(
        df,
        use_container_width=True
    )

    st.metric(
        "Total paper P&L",
        f"₹{df['Paper P&L'].sum():,.2f}"
    )

# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()

st.caption(
    "Educational research tool. No broker order execution "
    "is implemented. Quote availability and freshness are "
    "not guaranteed. This app is not a continuous monitor."
)


# ==========================================
# NIFTY OPTION CHAIN - READ ONLY
# ==========================================

st.divider()
st.header("📊 NIFTY Option Chain")
st.caption("Read-only market data. This section does not place orders.")

option_expiry = st.date_input(
    "Select NIFTY option expiry date",
    key="nifty_option_expiry"
)

if st.button("Fetch NIFTY Option Chain", key="fetch_nifty_chain"):
    access_token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")

    if not access_token:
        st.error("UPSTOX_ACCESS_TOKEN is missing from Streamlit Secrets.")
    else:
        try:
            with st.spinner("Fetching option-chain data..."):
                response = requests.get(
                    "https://api.upstox.com/v2/option/chain",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {access_token}"
                    },
                    params={
                        "instrument_key": "NSE_INDEX|Nifty 50",
                        "expiry_date": option_expiry.strftime("%Y-%m-%d")
                    },
                    timeout=20
                )

            if response.status_code != 200:
                st.error(
                    f"Upstox returned HTTP {response.status_code}. "
                    "Check the expiry date and API response."
                )
                st.code(response.text[:1500])

            else:
                payload = response.json()
                chain = payload.get("data", [])

                if not chain:
                    st.warning(
                        "No option-chain rows returned. "
                        "Select a valid listed expiry date."
                    )
                else:
                    rows = []

                    for item in chain:
                        call = item.get("call_options") or {}
                        put = item.get("put_options") or {}

                        call_market = call.get("market_data") or {}
                        put_market = put.get("market_data") or {}

                        rows.append({
                            "Strike": item.get("strike_price"),
                            "Call LTP": call_market.get("ltp"),
                            "Call OI": call_market.get("oi"),
                            "Call Volume": call_market.get("volume"),
                            "Put LTP": put_market.get("ltp"),
                            "Put OI": put_market.get("oi"),
                            "Put Volume": put_market.get("volume"),
                        })

                    df_chain = pd.DataFrame(rows)
                    df_chain = df_chain.sort_values(
                        "Strike", ascending=True
                    )

                    st.success(
                        f"Loaded {len(df_chain)} option-chain strikes."
                    )
                    st.dataframe(
                        df_chain,
                        use_container_width=True,
                        hide_index=True
                    )

                    st.caption(
                        "Prices and open interest are returned by Upstox. "
                        "Verify freshness and expiry before relying on them."
                    )

        except requests.RequestException as error:
            st.error(f"Network request failed: {error}")
        except (ValueError, TypeError, KeyError) as error:
            st.error(f"Could not process the option-chain response: {error}")

