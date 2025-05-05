import os
import secrets
import requests
from urllib.parse import urlencode
from flask import Blueprint, redirect, request, session, url_for, flash
from src.models import Account, Transaction, db
from flask_login import current_user, login_required
from dotenv import load_dotenv
from datetime import datetime, timedelta
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

oauth_bp = Blueprint("oauth", __name__)

CLIENT_ID = os.getenv("TRUELAYER_CLIENT_ID")
CLIENT_SECRET = os.getenv("TRUELAYER_CLIENT_SECRET")
REDIRECT_URI = os.getenv("TRUELAYER_REDIRECT_URI")

TRUELAYER_AUTH_URL = "https://auth.truelayer-sandbox.com"
TRUELAYER_API_URL = "https://api.truelayer-sandbox.com"

SCOPES = ["info", "accounts", "balance", "transactions"]

@oauth_bp.route("/connect")
@login_required
def connect_wallet():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state

    query = urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "providers": "mock",       # используем мок-банк
        "enable_mock": "true"
    })

    return redirect(f"{TRUELAYER_AUTH_URL}/?{query}")


@oauth_bp.route("/callback")
@login_required
def callback():
    if request.args.get("state") != session.get("oauth_state"):
        flash("State mismatch. Try again.")
        return redirect(url_for("dashboard"))

    code = request.args.get("code")
    if not code:
        flash("Authorization failed.")
        return redirect(url_for("dashboard"))

    # --- 1. Обмен кода на токен ---
    token_resp = requests.post(f"{TRUELAYER_AUTH_URL}/connect/token", data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code
    })

    if token_resp.status_code != 200:
        print("Token error:", token_resp.status_code, token_resp.text)
        flash("Token exchange failed.")
        return redirect(url_for("dashboard"))

    access_token = token_resp.json()["access_token"]
    session["access_token"] = access_token
    headers = {"Authorization": f"Bearer {access_token}"}

    # --- 2. Получение аккаунтов ---
    accounts_resp = requests.get(f"{TRUELAYER_API_URL}/data/v1/accounts", headers=headers)
    if accounts_resp.status_code != 200:
        print("Accounts fetch error:", accounts_resp.status_code, accounts_resp.text)
        flash("Failed to fetch accounts.")
        return redirect(url_for("dashboard"))

    accounts = accounts_resp.json().get("results", [])

    for acc in accounts:
        acc_id = acc["account_id"]
        acc_name = acc.get("display_name", acc.get("account_type", "Unnamed"))
        bank_name = acc.get("provider", {}).get("display_name", "Unknown")
        last4 = acc.get("account_number", {}).get("number", "")[-4:]

        # --- 2.1 Получение баланса ---
        balance_resp = requests.get(f"{TRUELAYER_API_URL}/data/v1/accounts/{acc_id}/balance", headers=headers)
        if balance_resp.status_code != 200:
            print("Balance fetch error:", balance_resp.status_code, balance_resp.text)
            continue

        balance_data = balance_resp.json().get("results", [])
        balance = balance_data[0].get("available", 0.0) if balance_data else 0.0

        # --- 2.2 Добавление аккаунта ---
        account = Account.query.filter_by(account_id=acc_id, user_id=current_user.id).first()
        if not account:
            account = Account(
                user_id=current_user.id,
                account_id=acc_id,
                account_name=acc_name,
                bank_name=bank_name,
                last4=last4,
                balance=balance
            )
            db.session.add(account)
            db.session.commit()  # для account.id

        # --- 3. Получение транзакций ---
        to_date = datetime.utcnow().date().isoformat()
        from_date = (datetime.utcnow().date() - timedelta(days=30)).isoformat()

        tx_url = f"{TRUELAYER_API_URL}/data/v1/accounts/{acc_id}/transactions"
        tx_params = {
            "from": from_date,
            "to": to_date
        }
        tx_resp = requests.get(tx_url, headers=headers, params=tx_params)

        if tx_resp.status_code != 200:
            print("Transaction fetch error:", tx_resp.status_code, tx_resp.text)
            continue

        txs = tx_resp.json().get("results", [])
        print(f"[DEBUG] {len(txs)} transactions for account {acc_name}")

        for tx in txs:
            amount = float(tx["amount"])
            timestamp = datetime.fromisoformat(tx["timestamp"].replace("Z", "+00:00"))
            description = tx.get("description", "")
            category = tx.get("transaction_category", "")

            # --- 3.1 Проверка дубликатов ---
            exists = Transaction.query.filter_by(
                account_id=account.id,
                amount=amount,
                date=timestamp,
                description=description
            ).first()

            if exists:
                continue

            transaction = Transaction(
                account_id=account.id,
                amount=amount,
                date=timestamp,
                description=description,
                category=category
            )
            db.session.add(transaction)

    db.session.commit()
    flash("Accounts and transactions imported successfully!", "success")
    return redirect(url_for("dashboard"))
