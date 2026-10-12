
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


# ==========================================
# AUTHENTICATION
# ==========================================

def get_access_token():
    """Read the Upstox access token from Streamlit Secrets."""
    try:
        token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")
    except Exception:
        token = ""

    if not token:
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "")

    token = str(token).strip() if token else ""

    if not token:
        raise ValueError(
            "UPSTOX_ACCESS_TOKEN is missing. "
            "Add it under Streamlit App Settings > Secrets."
        )

    return token


def get_headers():
    """Create authenticated request headers."""
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_access_token()}",
    }


# ==========================================
# COMMON GET REQUEST
# ==========================================

def api_get(endpoint, params=None):
    """Call an Upstox V2 GET endpoint and return its data."""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(
            url,
            headers=get_headers(),
            params=params or {},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 401:
            raise ValueError(
                "Upstox access token is invalid or expired. "
                "Refresh it and update Streamlit Secrets."
            )

        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "success":
            raise ValueError(
                str(
                    payload.get(
                        "errors",
                        "Upstox API request failed.",
                    )
                )[:600]
            )

        return payload.get("data")

    except requests.exceptions.Timeout as exc:
        raise ValueError(
            "Upstox request timed out. Please try again."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        status = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )
        raise ValueError(
            f"Upstox HTTP error: {status}"
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise ValueError(
            f"Could not connect to Upstox: {exc}"
        ) from exc

    except ValueError:
        raise


# ==========================================
# LIVE MARKET QUOTES
# ==========================================

def get_market_quote(instrument_keys):
    """
    Fetch market quotes.

    Example:
        get_market_quote("NSE_INDEX|Nifty 50")
    """
    if isinstance(instrument_keys, str):
        instrument_keys = [instrument_keys]

    if not instrument_keys:
        raise ValueError(
            "Provide at least one instrument key."
        )

    keys = [
        str(key).strip()
        for key in instrument_keys
        if str(key).strip()
    ]

    if not keys:
        raise ValueError(
            "No valid instrument keys were provided."
        )

    return api_get(
        "market-quote/quotes",
        params={
            "instrument_key": ",".join(keys)
        },
    )


# ==========================================
# OPTION CONTRACTS / EXPIRIES
# ==========================================

def get_option_contracts(
    instrument_key=NIFTY_KEY,
):
    """
    Fetch option contracts for an underlying.

    Example underlying:
        NSE_INDEX|Nifty 50
    """
    if not instrument_key:
        raise ValueError(
            "Underlying instrument key is required."
        )

    return api_get(
        "option/contract",
        params={
            "instrument_key": instrument_key
        },
    )


def get_expiry_dates(
    instrument_key=NIFTY_KEY,
    include_expired=False,
):
    """Return sorted unique expiry dates as YYYY-MM-DD strings."""
    contracts = get_option_contracts(instrument_key)

    if not isinstance(contracts, list):
        raise ValueError(
            "Unexpected option-contract response."
        )

    today = date.today().isoformat()

    expiries = set()

    for item in contracts:
        expiry = item.get("expiry")

        if not expiry:
            continue

        expiry = str(expiry)

        if include_expired or expiry >= today:
            expiries.add(expiry)

    return sorted(expiries)


# ==========================================
# OPTION CHAIN
# ==========================================

def get_option_chain(
    instrument_key,
    expiry_date,
):
    """
    Fetch an option chain for a selected expiry.

    expiry_date must use YYYY-MM-DD format.
    """
    if not instrument_key:
        raise ValueError(
            "Underlying instrument key is required."
        )

    if not expiry_date:
        raise ValueError(
            "Option expiry date is required."
        )

    return api_get(
        "option/chain",
        params={
            "instrument_key": instrument_key,
            "expiry_date": str(expiry_date),
        },
    )


# ==========================================
# HISTORICAL CANDLES
# ==========================================

def get_historical_candles(
    instrument_key=NIFTY_KEY,
    interval="1minute",
    to_date=None,
    from_date=None,
):
    """
    Fetch historical candle data using Upstox V2.

    Dates use YYYY-MM-DD format.
    Results are returned in the API's original format.

    Supported intervals in this helper:
        1minute, 30minute, day, week, month

    Each candle commonly contains:
        timestamp, open, high, low, close, volume, open interest
    """
    if not instrument_key:
        raise ValueError(
            "Instrument key is required."
        )

    allowed_intervals = {
        "1minute",
        "30minute",
        "day",
        "week",
        "month",
    }

    if interval not in allowed_intervals:
        raise ValueError(
            "Unsupported interval. Choose: "
            + ", ".join(sorted(allowed_intervals))
        )

    today = date.today()

    if to_date is None:
        to_date = today.isoformat()

    if from_date is None:
        from_date = (
            today - timedelta(days=7)
        ).isoformat()

    # Validate date strings before making a request.
    try:
        start = date.fromisoformat(str(from_date))
        end = date.fromisoformat(str(to_date))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Dates must use YYYY-MM-DD format."
        ) from exc

    if start > end:
        raise ValueError(
            "from_date cannot be after to_date."
        )

    encoded_key = quote(
        str(instrument_key),
        safe="",
    )

    endpoint = (
        f"{BASE_URL}/historical-candle/"
        f"{encoded_key}/{interval}/"
        f"{end.isoformat()}/{start.isoformat()}"
    )

    try:
        response = requests.get(
            endpoint,
            headers=get_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 401:
            raise ValueError(
                "Upstox access token is invalid or expired."
            )

        response.raise_for_status()
        payload = response.json()

        if payload.get("status") != "success":
            raise ValueError(
                str(
                    payload.get(
                        "errors",
                        "Historical-candle request failed.",
                    )
                )[:600]
            )

        data = payload.get("data") or {}
        candles = data.get("candles", [])

        if not isinstance(candles, list):
            raise ValueError(
                "Unexpected historical-candle response."
            )

        return candles

    except requests.exceptions.Timeout as exc:
        raise ValueError(
            "Historical-candle request timed out."
        ) from exc

    except requests.exceptions.HTTPError as exc:
        status = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )
        raise ValueError(
            f"Historical-candle HTTP error: {status}"
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise ValueError(
            f"Could not fetch historical candles: {exc}"
        ) from exc

    except ValueError:
        raise
