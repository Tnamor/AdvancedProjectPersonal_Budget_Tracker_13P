import requests
from flask import session, abort
from datetime import datetime, timedelta


API_BASE = "https://api.truelayer-sandbox.com"

def get_token():
    token = session.get("access_token")
    if not token:
        abort(401, description="Access token not found in session.")
    return token

def get_headers(token=None):
    token = token or get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_accounts(token=None):
    headers = get_headers(token)
    response = requests.get(f"{API_BASE}/data/v1/accounts", headers=headers)
    try:
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.HTTPError as e:
        print("Error fetching accounts:", e, response.text)
        raise


def get_transactions(account_id, token=None):
    headers = get_headers(token)

    # Диапазон дат: последние 30 дней
    to_date = datetime.utcnow().date().isoformat()
    from_date = (datetime.utcnow() - timedelta(days=30)).date().isoformat()

    url = f"{API_BASE}/data/v1/accounts/{account_id}/transactions"
    params = {
        "from": from_date,
        "to": to_date
    }

    response = requests.get(url, headers=headers, params=params)

    try:
        response.raise_for_status()
        return response.json().get("results", [])
    except requests.HTTPError as e:
        print(f"Error fetching transactions for account {account_id}:", e, response.text)
        raise
