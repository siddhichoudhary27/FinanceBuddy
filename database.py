import streamlit as st
import pandas as pd
from supabase import create_client


@st.cache_resource
def get_supabase_client():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


def add_transaction(
    user_id,
    transaction_date,
    transaction_type,
    description,
    category,
    amount,
    currency,
    exchange_rate_to_usd,
):
    amount = float(amount)
    rate = float(exchange_rate_to_usd)
    if amount <= 0:
        raise ValueError("Transaction amount must be greater than zero.")
    if rate <= 0:
        raise ValueError("Exchange rate must be greater than zero.")

    data = {
        "user_id": user_id,
        "transaction_date": str(transaction_date),
        "type": transaction_type.lower(),
        "description": (description or "").strip(),
        "category": category,
        "amount": amount,
        "currency": currency.upper(),
        "exchange_rate_to_usd": rate,
        "amount_usd": round(amount * rate, 2),
    }

    return get_supabase_client().table("transactions").insert(data).execute()


def get_transactions(user_id):
    response = (
        get_supabase_client()
        .table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("transaction_date", desc=True)
        .execute()
    )
    return pd.DataFrame(response.data or [])


def get_financial_summary(user_id):
    df = get_transactions(user_id)
    if df.empty:
        return {
            "income_usd": 0.0,
            "expenses_usd": 0.0,
            "balance_usd": 0.0,
        }

    df["amount_usd"] = pd.to_numeric(df["amount_usd"], errors="coerce").fillna(0)
    types = df["type"].astype(str).str.lower()
    income = df.loc[types == "income", "amount_usd"].sum()
    expenses = df.loc[types == "expense", "amount_usd"].sum()

    return {
        "income_usd": round(float(income), 2),
        "expenses_usd": round(float(expenses), 2),
        "balance_usd": round(float(income - expenses), 2),
    }
