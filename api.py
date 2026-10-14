"""
NIFTY Quant Lab - Upstox API helper
READ-ONLY: Does not place, modify, or cancel orders.
"""
import os
from datetime import date, timedelta
from urllib.parse import quote
import requests
import streamlit as st

BASE_URL = "https://api.upstox.com/v2"
REQUEST_TIMEOUT = 20
NIFTY_KEY = "NSE_INDEX|Nifty 50"

def get_access_token():
    try:
        token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")
    except Exception:
        token = ""
    if not token:
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "")
    token = str(token).strip() if token else ""
    if not token:
        raise ValueError("UPSTOX_ACCESS_TOKEN is missing. Add it under Streamlit App Settings > Secrets.")
    return token

def get_headers():
    return {"Accept": "application/json", "Authorization": f"Bearer {get_access_token()}"}

def _request_json(url, params=None):
    try:
        response = requests.get(url, headers=get_headers(), params=params or {}, timeout=REQUEST_TIMEOUT)
        if response.status_code == 401:
            raise ValueError("Upstox access token is invalid or expired. Refresh it and update Streamlit Secrets.")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != "success":
            detail = payload.get("errors", "Upstox API request failed.") if isinstance(payload, dict) else "Unexpected API response."
            raise ValueError(str(detail)[:600])
        return payload.get("data")
    except requests.exceptions.Timeout as exc:
        raise ValueError("Upstox request timed out. Please try again.") from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise ValueError(f"Upstox HTTP error: {status}") from exc
    except requests.exceptions.RequestException as exc:
        raise ValueError(f"Could not connect to Upstox: {exc}") from exc

def api_get(endpoint, params=None):
    return _request_json(f"{BASE_URL}/{endpoint.lstrip('/')}", params=params)

def get_market_quote(instrument_keys):
    if isinstance(instrument_keys, str):
        instrument_keys = [instrument_keys]
    keys = [str(k).strip() for k in (instrument_keys or []) if str(k).strip()]
    if not keys:
        raise ValueError("Provide at least one instrument key.")
    return api_get("market-quote/quotes", {"instrument_key": ",".join(keys)})

def get_option_contracts(instrument_key=NIFTY_KEY):
    if not instrument_key:
        raise ValueError("Underlying instrument key is required.")
    return api_get("option/contract", {"instrument_key": instrument_key})

def get_expiry_dates(instrument_key=NIFTY_KEY, include_expired=False):
    contracts = get_option_contracts(instrument_key)
    if not isinstance(contracts, list):
        raise ValueError("Unexpected option-contract response.")
    today = date.today().isoformat()
    expiries = set()
    for item in contracts:
        if not isinstance(item, dict):
            continue
        expiry = item.get("expiry")
        if expiry:
            expiry = str(expiry)[:10]
            if include_expired or expiry >= today:
                expiries.add(expiry)
    return sorted(expiries)

def get_option_chain(instrument_key, expiry_date):
    if not instrument_key or not expiry_date:
        raise ValueError("Underlying instrument key and option expiry date are required.")
    return api_get("option/chain", {"instrument_key": instrument_key, "expiry_date": str(expiry_date)})

def _validate_instrument_and_interval(instrument_key, interval):
    if not instrument_key:
        raise ValueError("Instrument key is required.")
    allowed = {"1minute", "30minute", "day", "week", "month"}
    if interval not in allowed:
        raise ValueError("Unsupported interval. Choose: " + ", ".join(sorted(allowed)))

def get_historical_candles(instrument_key=NIFTY_KEY, interval="1minute", to_date=None, from_date=None):
    _validate_instrument_and_interval(instrument_key, interval)
    today = date.today()
    to_date = today.isoformat() if to_date is None else str(to_date)
    from_date = (today - timedelta(days=7)).isoformat() if from_date is None else str(from_date)
    try:
        start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dates must use YYYY-MM-DD format.") from exc
    if start > end:
        raise ValueError("from_date cannot be after to_date.")
    encoded_key = quote(str(instrument_key), safe="")
    url = f"{BASE_URL}/historical-candle/{encoded_key}/{interval}/{end.isoformat()}/{start.isoformat()}"
    data = _request_json(url)
    candles = data.get("candles", []) if isinstance(data, dict) else []
    if not isinstance(candles, list):
        raise ValueError("Unexpected historical-candle response.")
    return candles

def get_intraday_candles(instrument_key=NIFTY_KEY, interval="1minute"):
    """Fetch current-day candles; the caller must still validate timestamps."""
    _validate_instrument_and_interval(instrument_key, interval)
    encoded_key = quote(str(instrument_key), safe="")
    url = f"{BASE_URL}/historical-candle/intraday/{encoded_key}/{interval}"
    data = _request_json(url)
    candles = data.get("candles", []) if isinstance(data, dict) else []
    if not isinstance(candles, list):
        raise ValueError("Unexpected intraday-candle response.")
    return candles
