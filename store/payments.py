"""M-Pesa Daraja STK Push integration.

Live mode activates when DARAJA_KEY / DARAJA_SECRET / DARAJA_SHORTCODE /
DARAJA_PASSKEY / DARAJA_CALLBACK env vars are set. Otherwise the store runs in
demo mode: the checkout page shows a simulated STK prompt that auto-confirms, so
the full flow can be tested without Safaricom credentials. (An initiator name is
only needed for the B2C APIs — STK Push never asks for one.)

DARAJA_CALLBACK is the publicly reachable HTTPS URL Safaricom posts the PIN result
to: https://your-domain/mpesa/callback/<MPESA_CALLBACK_SECRET>/. Safaricom sends no
authentication header on an STK callback, so that secret path segment is the only
thing between a stranger and a flipped-to-paid order; it is compared, never logged.
"""

import base64
import json
import os
import secrets
import time
import urllib.request
from datetime import datetime, timedelta, timezone

CONSUMER_BASE = os.environ.get("DARAJA_BASE", "https://sandbox.safaricom.co.ke")

BUSINESS_SHORTCODE = os.environ.get("DARAJA_SHORTCODE", "")
PASSKEY = os.environ.get("DARAJA_PASSKEY", "")
KEY = os.environ.get("DARAJA_KEY", "")
SECRET = os.environ.get("DARAJA_SECRET", "")
CALLBACK_URL = os.environ.get("DARAJA_CALLBACK", "")
CALLBACK_SECRET = os.environ.get("MPESA_CALLBACK_SECRET", "")

LIVE = bool(BUSINESS_SHORTCODE and PASSKEY and KEY and SECRET and CALLBACK_URL)

_token_cache = {"token": None, "expires": 0}


def mpesa_mode():
    return "live" if LIVE else "demo"


def callback_authorized(token):
    """True only when the URL carries the secret from MPESA_CALLBACK_SECRET; unset means refuse."""
    return bool(CALLBACK_SECRET) and secrets.compare_digest(token, CALLBACK_SECRET)


def _post_json(url, payload, headers=None):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _get_json(url, headers=None):
    """Daraja's OAuth endpoint is GET-only: POSTing an empty body answers 200 with '{}' and no token."""
    req = urllib.request.Request(url, None, headers or {})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _get_token():
    now = time.time()
    if _token_cache["token"] and _token_cache["expires"] > now + 30:
        return _token_cache["token"]
    creds = base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    resp = _get_json(
        f"{CONSUMER_BASE}/oauth/v1/generate?grant_type=client_credentials",
        {"Authorization": f"Basic {creds}"},
    )
    token = resp.get("access_token")
    if not token:
        # A CDN or proxy in front of Daraja can answer 200 with an empty body; say so instead of
        # failing later with a bare KeyError deep inside the checkout.
        raise RuntimeError(f"Daraja returned no access_token: {resp or 'empty response'}")
    _token_cache.update(token=token, expires=now + int(resp.get("expires_in", 3600)))
    return token


def _normalize_phone(phone):
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("254"):
        return digits
    if digits.startswith("0"):
        return "254" + digits[1:]
    if digits.startswith("7") or digits.startswith("1"):
        return "254" + digits
    return digits


def _password():
    return base64.b64encode(f"{BUSINESS_SHORTCODE}{PASSKEY}{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}".encode()).decode()


def initiate_stk(phone, amount, order_reference, description="Zuri Luxee order"):
    """Trigger STK push. Returns (ok, checkout_request_id_or_error)."""
    if not LIVE:
        return True, f"DEMO-{order_reference}"
    try:
        resp = _post_json(
            f"{CONSUMER_BASE}/mpesa/stkpush/v1/processrequest",
            {
                "BusinessShortCode": BUSINESS_SHORTCODE,
                "Password": _password(),
                "Timestamp": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(amount),
                "PartyA": _normalize_phone(phone),
                "PartyB": BUSINESS_SHORTCODE,
                "PhoneNumber": _normalize_phone(phone),
                "CallBackURL": CALLBACK_URL or f"{CONSUMER_BASE}/",
                "AccountReference": order_reference,
                "TransactionDesc": description[:60],
            },
            {"Authorization": f"Bearer {_get_token()}"},
        )
        if resp.get("ResponseCode") == "0":
            return True, resp.get("CheckoutRequestID", "")
        return False, resp.get("ErrorMessage", "STK push failed")
    except Exception as exc:  # noqa: BLE001 - surface any network/API error to the UI
        return False, str(exc)


def query_stk(checkout_request_id):
    """Returns (status, mpesa_reference_or_blank): status in pending/success/failed."""
    if not LIVE:
        return "success", "DEMO" + secrets.token_hex(5).upper()
    try:
        resp = _post_json(
            f"{CONSUMER_BASE}/mpesa/stkpushquery/v1/query",
            {
                "BusinessShortCode": BUSINESS_SHORTCODE,
                "Password": _password(),
                "Timestamp": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "CheckoutRequestID": checkout_request_id,
            },
            {"Authorization": f"Bearer {_get_token()}"},
        )
    except Exception:  # noqa: BLE001
        return "pending", ""
    code = resp.get("ResponseCode")
    result = resp.get("ResultDesc", "")
    if code == "0" and "success" in result.lower():
        receipt = ""
        for item in resp.get("QueryResult", {}).get("Result", []):
            if item.get("Name") == "MpesaReceiptNumber":
                receipt = item.get("Value", "")
        return "success", receipt
    if code in ("1", "2", "4", "5") or "cancel" in result.lower() or "fail" in result.lower():
        return "failed", ""
    return "pending", ""
