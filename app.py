
import requests
from urllib.parse import quote

# ==========================================
# NIFTY QUANT LAB - UPSTOX API MODULE
# READ-ONLY MARKET DATA
# ==========================================

BASE_URL = "https://api.upstox.com/v2"
NIFTY_INDEX_KEY = "NSE_INDEX|Nifty 50"
REQUEST_TIMEOUT = 20


class UpstoxAPIError(Exception):
    """Raised when an Upstox API request fails."""
    pass


class UpstoxAPI:
    def __init__(self, access_token):
        if not access_token or not access_token.strip():
            raise ValueError("Upstox access token is missing.")

        self.access_token = access_token.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        })

    def _get(self, endpoint, params=None):
        """Make an authenticated GET request."""
        url = f"{BASE_URL}{endpoint}"

        try:
            response = self.session.get(
                url,
                params=params or {},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise UpstoxAPIError(
                f"Network request failed: {exc}"
            ) from exc

        if response.status_code != 200:
            # Do not expose request headers or authentication tokens.
            raise UpstoxAPIError(
                f"Upstox returned HTTP {response.status_code}: "
                f"{response.text[:800]}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstoxAPIError(
                "Upstox returned an invalid JSON response."
            ) from exc

        if payload.get("status") == "error":
            raise UpstoxAPIError(
                f"Upstox API error: {payload.get('errors', 'Unknown error')}"
            )

        return payload.get("data")

    def get_nifty_quote(self):
        """Fetch the latest available NIFTY 50 quote."""
        data = self._get(
            "/market-quote/quotes",
            {"instrument_key": NIFTY_INDEX_KEY},
        )

        if not isinstance(data, dict) or not data:
            raise UpstoxAPIError("No NIFTY quote returned.")

        quote_data = next(iter(data.values()))
        ltp = quote_data.get("last_price")

        if ltp is None:
            raise UpstoxAPIError(
                "NIFTY quote does not contain last_price."
            )

        return {
            "instrument": "NIFTY 50",
            "instrument_key": NIFTY_INDEX_KEY,
            "last_price": float(ltp),
            "raw": quote_data,
        }

    def get_option_contracts(self):
        """Fetch listed NIFTY option contracts."""
        data = self._get(
            "/option/contract",
            {"instrument_key": NIFTY_INDEX_KEY},
        )

        if not isinstance(data, list):
            raise UpstoxAPIError(
                "Unexpected option-contract response."
            )

        return data

    def get_expiry_dates(self):
        """Return sorted expiry dates provided by Upstox."""
        contracts = self.get_option_contracts()

        expiries = {
            str(item["expiry"])
            for item in contracts
            if item.get("expiry")
        }

        return sorted(expiries)

    def get_option_chain(self, expiry_date):
        """
        Fetch the option chain for an expiry date.
        expiry_date format: YYYY-MM-DD
        """
        if not expiry_date:
            raise ValueError("An expiry date is required.")

        data = self._get(
            "/option/chain",
            {
                "instrument_key": NIFTY_INDEX_KEY,
                "expiry_date": str(expiry_date),
            },
        )

        if not isinstance(data, list):
            raise UpstoxAPIError(
                "Unexpected option-chain response."
            )

        return data

    def get_intraday_candles(
        self,
        instrument_key=NIFTY_INDEX_KEY,
        interval=1,
    ):
        """
        Fetch today's intraday candles.

        interval is in minutes. Confirm that the selected interval
        is supported by Upstox for this endpoint.
        """
        if not isinstance(interval, int) or interval <= 0:
            raise ValueError("Interval must be a positive integer.")

        encoded_key = quote(instrument_key, safe="")
        endpoint = (
            f"/historical-candle/intraday/"
            f"{encoded_key}/minutes/{interval}"
        )

        data = self._get(endpoint)

        if not isinstance(data, dict):
            raise UpstoxAPIError(
                "Unexpected intraday-candle response."
            )

        candles = data.get("candles", [])

        return [
            {
                "timestamp": candle[0],
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
                "open_interest": (
                    candle[6] if len(candle) > 6 else None
                ),
            }
            for candle in candles
        ]

    def close(self):
        """Close the underlying HTTP session."""
        self.session.close()
