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
"READ-ONLY MODE: No live orders are placed, modified, "
"or cancelled by this app."
)

--------------------------------------------------

UPSTOX READ-ONLY QUOTE

--------------------------------------------------

st.subheader("🔌 Upstox Connection")

def get_upstox_quote():
"""Fetch a read-only NIFTY 50 quote."""

try:
    token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")

    if not token:
        return None, (
            "Access token is missing. Check Streamlit Secrets."
        )

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    url = (
        "https://api.upstox.com/v2/market-quote/quotes"
    )

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
            "Check token validity and API permissions."
        )

    payload = response.json()
    data = payload.get("data", {})

    if not data:
        return None, (
            "No quote returned. Check the instrument key "
            "and the Upstox API response."
        )

    quote = next(iter(data.values()), None)

    if not isinstance(quote, dict):
        return None, "Unexpected quote response format."

    last_price = quote.get("last_price")

    if last_price is None:
        return None, "The response did not contain a last price."

    return float(last_price), None

except requests.Timeout:
    return None, "Upstox request timed out. Try again."

except requests.RequestException:
    return None, (
        "Could not connect to Upstox. Check your connection."
    )

except Exception:
    return None, (
        "Quote check failed. Check app configuration "
        "and Streamlit Secrets."
    )

if st.button("Test Upstox connection / Refresh NIFTY quote"):
with st.spinner("Checking Upstox..."):
quote, error = get_upstox_quote()

if error:
    st.error(error)
else:
    st.success("Upstox quote request succeeded.")
    st.metric("NIFTY 50 quote (₹)", f"{quote:,.2f}")

    st.caption(
        "Confirm market status and quote freshness. "
        "This is a manual refresh, not continuous monitoring."
    )

st.divider()

--------------------------------------------------

MANUAL MARKET INPUTS

--------------------------------------------------

st.subheader("📊 Market Inputs")

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
            "Planning calculation only. Charges, slippage "
            "and gap risk are excluded."
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
"Educational research tool. No broker order execution "
"is implemented. Market data may be unavailable or delayed. "
"Do not rely on this app alone for trading decisions."
)
