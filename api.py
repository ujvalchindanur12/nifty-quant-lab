
import os
import requests
import streamlit as st


BASE_URL = "https://api.upstox.com/v2"


def get_access_token():
    """Read the Upstox access token from Streamlit Secrets."""
    try:
        token = st.secrets.get("UPSTOX_ACCESS_TOKEN", "")
    except Exception:
        token = ""

    if not token:
        token = os.getenv("UPSTOX_ACCESS_TOKEN", "")

    if not token:
        raise ValueError(
            "UPSTOX_ACCESS_TOKEN is missing. "
            "Add it in Streamlit Secrets."
        )

    return token


def get_headers():
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_access_token()}",
    }


def api_get(endpoint, params=None):
    """Send a GET request to Upstox and return its data."""
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"

    try:
        response = requests.get(
            url,
            headers=get_headers(),
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("status") != "success":
            raise ValueError(
                result.get("errors", "Upstox API request failed")
            )

        return result.get("data")

    except requests.exceptions.HTTPError as exc:
        status = (
            exc.response.status_code
            if exc.response is not None
            else "unknown"
        )

        if status == 401:
            raise ValueError(
                "Upstox access token is invalid or expired. "
                "Refresh the token and update Streamlit Secrets."
            ) from exc

        raise ValueError(
            f"Upstox HTTP error: {status}"
        ) from exc

    except requests.exceptions.RequestException as exc:
        raise ValueError(
            f"Could not connect to Upstox: {exc}"
        ) from exc


def get_market_quote(instrument_keys):
    """
    Fetch quotes for instrument keys.

    Example:
    get_market_quote([
        "NSE_INDEX|Nifty 50"
    ])
    """
    if isinstance(instrument_keys, str):
        instrument_keys = [instrument_keys]

    if not instrument_keys:
        raise ValueError("Provide at least one instrument key.")

    return api_get(
        "market-quote/quotes",
        params={"instrument_key": ",".join(instrument_keys)},
    )


def get_option_contracts(instrument_key):
    """
    Get available option contracts for an underlying.
    Example underlying: NSE_INDEX|Nifty 50
    """
    if not instrument_key:
        raise ValueError("Underlying instrument key is required.")

    return api_get(
        "option/contract",
        params={"instrument_key": instrument_key},
    )


def get_option_chain(instrument_key, expiry_date):
    """
    Fetch an option chain for a selected expiry.

    expiry_date must use YYYY-MM-DD format.
    """
    if not instrument_key or not expiry_date:
        raise ValueError(
            "Underlying instrument key and expiry date are required."
        )

    return api_get(
        "option/chain",
        params={
            "instrument_key": instrument_key,
            "expiry_date": expiry_date,
        },
    )
