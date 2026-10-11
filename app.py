
import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="NIFTY Quant Lab",
    page_icon="📈",
    layout="wide"
)

st.title("📈 NIFTY Quant Lab")
st.caption("NIFTY options research and risk dashboard")

st.warning(
    "Research mode: no live orders are placed. "
    "Prices entered manually are not live market data."
)

st.subheader("Market inputs")

col1, col2 = st.columns(2)

with col1:
    nifty = st.number_input(
        "NIFTY spot price",
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

st.subheader("Risk controls")

risk_pct = st.slider(
    "Maximum planned risk per trade (%)",
    min_value=0.5,
    max_value=2.0,
    value=1.0,
    step=0.5
)

risk_amount = capital * risk_pct / 100

st.metric("Planned risk budget", f"₹{risk_amount:,.0f}")
st.metric("Entered NIFTY level", f"{nifty:,.2f}")

st.subheader("Trade planning")

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
        st.error("Entry premium must be above stop-loss premium.")
    elif stop_premium < 0:
        st.error("Stop-loss cannot be negative.")
    else:
        loss_per_unit = premium - stop_premium
        loss_per_lot = loss_per_unit * lot_size
        max_lots = int(risk_amount // loss_per_lot)

        st.metric("Estimated loss per lot", f"₹{loss_per_lot:,.2f}")
        st.metric("Lots within risk budget", max_lots)

        if max_lots == 0:
            st.warning("One lot exceeds your planned risk budget.")
        else:
            st.info(
                "This is a calculation, not a trading signal. "
                "It excludes charges, slippage and gap risk."
            )

st.subheader("Paper-trade journal")

if "trades" not in st.session_state:
    st.session_state.trades = []

with st.form("paper_trade_form"):
    symbol = st.text_input("Instrument", "NIFTY")
    side = st.selectbox("Position", ["BUY CE", "BUY PE"])
    entry = st.number_input("Paper entry premium", min_value=0.0, value=100.0)
    exit_price = st.number_input("Paper exit premium", min_value=0.0, value=105.0)
    quantity = st.number_input("Quantity in units", min_value=1, value=1)

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
    st.dataframe(df, use_container_width=True)
    st.metric("Total paper P&L", f"₹{df['Paper P&L'].sum():,.2f}")

st.caption(
    "Educational tool only. Not investment advice. "
    "No broker connection or live order execution is implemented."
)
