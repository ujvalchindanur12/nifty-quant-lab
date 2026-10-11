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
st.caption("NIFTY options research, live-data connection and risk dashboard")

--------------------------------------------------

SAFETY: READ-ONLY MODE

--------------------------------------------------

st.warning(
"READ-ONLY MODE: This app does not place, modify, "
"or cancel broker orders. Verify all prices before trading."
)

--------------------------------------------------

UPSTOX CONFIGURATION

--------------------------------------------------

st.subheader("🔌 Upstox Connection")

def get_upstox_quote():
"""Fetch a read-only NIFTY index quote from Upstox."""

try:
    token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")

    if not token:
        return None, (
            "Access token is missing. Add a valid "
            "UPSTOX_ACCESS_TOKEN in Streamlit Secrets."
        )

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    # Upstox V2 full market quote endpoint.
    # Nifty 50 instrument key:
    # NSE_INDEX|Nifty 50
    url = "https://api.upstox.com/v2/market-quote/quotes"

    params = {
        "instrument_key": "NSE_INDEX|Nifty 50"
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=15
    )

    if response.status_code != 200:
        return None, (
            f"Upstox returned HTTP {response.status_code}. "
            "Check token validity and API permissions. "
            "The response body is hidden to avoid exposing "
            "account or authentication details."
        )

    payload = response.json()
    data = payload.get("data", {})

    if not data:
        return None, (
            "Upstox returned no quote data. "
            "The instrument key or endpoint may need checking."
        )

    # Locate the returned quote without assuming
    # the exact dictionary key format.
    quote = next(iter(data.values()), None)

    if not isinstance(quote, dict):
        return None, "The quote response format was unexpected."

    last_price = quote.get("last_price")

    if last_price is None:
        return None, "No last price was returned by Upstox."

    return {
        "last_price": float(last_price),
        "raw_quote": quote
    }, None

except requests.Timeout:
    return None, "Upstox request timed out. Please try again."

except requests.RequestException:
    return None, (
        "Could not reach Upstox. Check your internet connection "
        "and try again."
    )

except Exception:
    return None, (
        "The quote could not be processed. Check the app "
        "configuration and try again."
    )

if st.button("Test Upstox connection / Refresh NIFTY quote"):
with st.spinner("Checking Upstox..."):
quote, error = get_upstox_quote()

if error:
    st.error(error)
else:
    st.success("Upstox quote request succeeded.")
    st.metric(
        "Live NIFTY 50 quote (₹)",
        f"{quote['last_price']:,.2f}"
    )
    st.caption(
        "Retrieved from Upstox. Confirm the exchange timestamp "
        "and market status before relying on this price."
    )

st.caption(
"The quote appears only after you press the refresh button. "
"This is not a continuous real-time monitoring service."
)

st.divider()

--------------------------------------------------

MANUAL MARKET INPUTS

--------------------------------------------------

st.subheader("📊 Market Inputs")

col1, col2 = st.columns(2)

with col1:
nifty = st.number_input(
"NIFTY spot price (manual fallback)",
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

--------------------------------------------------

RISK CONTROLS

--------------------------------------------------

st.subheader("🛡️ Risk Controls")

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
st.metric("Planned risk budget", f"₹{risk_amount:,.0f}")

with col2:
st.metric("Manual NIFTY level", f"{nifty:,.2f}")

--------------------------------------------------

TRADE RISK CALCULATOR

--------------------------------------------------

st.subheader("🧮 Trade Planning")

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
            "Calculation only, not a trading signal. "
            "Charges, slippage and gap risk are excluded."
        )

--------------------------------------------------

PAPER-TRADE JOURNAL

--------------------------------------------------

st.subheader("📝 Paper-Trade Journal")

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

--------------------------------------------------

FOOTER

--------------------------------------------------

st.divider()

st.caption(
"Educational research tool. No broker order execution is "
"implemented. Market data may be delayed or unavailable. "
"Do not rely on this app alone to make trading decisions."
)
