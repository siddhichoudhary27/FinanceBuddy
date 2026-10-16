import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import date
from database import (
    get_supabase_client,
    add_transaction,
    get_transactions,
    get_financial_summary,
)

st.set_page_config(page_title="FinanceBuddy", page_icon="💚", layout="wide")
supabase = get_supabase_client()

CURRENCIES = {
    "INR": {"name": "Indian Rupee", "symbol": "₹", "flag": "🇮🇳"},
    "USD": {"name": "US Dollar", "symbol": "$", "flag": "🇺🇸"},
    "EUR": {"name": "Euro", "symbol": "€", "flag": "🇪🇺"},
    "GBP": {"name": "British Pound", "symbol": "£", "flag": "🇬🇧"},
    "AUD": {"name": "Australian Dollar", "symbol": "A$", "flag": "🇦🇺"},
    "CAD": {"name": "Canadian Dollar", "symbol": "C$", "flag": "🇨🇦"},
    "SGD": {"name": "Singapore Dollar", "symbol": "S$", "flag": "🇸🇬"},
    "AED": {"name": "UAE Dirham", "symbol": "د.إ", "flag": "🇦🇪"},
    "JPY": {"name": "Japanese Yen", "symbol": "¥", "flag": "🇯🇵"},
    "NZD": {"name": "New Zealand Dollar", "symbol": "NZ$", "flag": "🇳🇿"},
    "CHF": {"name": "Swiss Franc", "symbol": "CHF", "flag": "🇨🇭"},
    "CNY": {"name": "Chinese Yuan", "symbol": "¥", "flag": "🇨🇳"},
    "HKD": {"name": "Hong Kong Dollar", "symbol": "HK$", "flag": "🇭🇰"},
    "THB": {"name": "Thai Baht", "symbol": "฿", "flag": "🇹🇭"},
}
CURRENCY_CODES = list(CURRENCIES.keys())

st.markdown(
    """
    <style>
  

/* Make form fields readable */
.stApp input,
.stApp textarea,
.stApp [data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    color: #19352A !important;
    -webkit-text-fill-color: #19352A !important;
    border-color: #B7CBB9 !important;
}

.stApp input::placeholder,
.stApp textarea::placeholder {
    color: #64756B !important;
    -webkit-text-fill-color: #64756B !important;
    opacity: 1 !important;
}

/* Make buttons readable */
div.stButton > button,
div.stFormSubmitButton > button {
    background-color: #217A46 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    border-color: #217A46 !important;
}

    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_rates(base_currency):
    """Fetch current rates: one unit of base_currency equals rates[code] units."""
    base_currency = base_currency.upper()
    response = requests.get(f"https://open.er-api.com/v6/latest/{base_currency}", timeout=12)
    response.raise_for_status()
    payload = response.json()
    if payload.get("result") != "success" or "rates" not in payload:
        raise ValueError(f"The exchange-rate service did not return rates for {base_currency}.")
    return payload["rates"], payload.get("time_last_update_utc", "recent update")


def get_rate(from_currency, to_currency):
    """Return units of target currency per one unit of source currency."""
    from_currency, to_currency = from_currency.upper(), to_currency.upper()
    if from_currency == to_currency:
        return 1.0, "Same currency"
    rates, updated = fetch_rates(from_currency)
    rate = float(rates[to_currency])
    if rate <= 0:
        raise ValueError("The exchange-rate service returned an invalid rate.")
    return rate, updated


def fmt_money(amount, currency):
    symbol = CURRENCIES.get(currency, {}).get("symbol", f"{currency} ")
    return f"{symbol}{float(amount):,.2f}"


def save_profile(user, full_name=""):
    if not user:
        return
    try:
        supabase.table("profiles").upsert({"id": user.id, "full_name": full_name}).execute()
    except Exception:
        pass


def show_dashboard():
    user = st.session_state.user
    user_id = user.id

    st.sidebar.title("💚 FinanceBuddy")
    st.sidebar.caption("Your money, made clearer")
    st.sidebar.success("Signed in")
    st.sidebar.caption(user.email or "")
    if st.sidebar.button("Log out"):
        try:
            supabase.auth.sign_out()
        finally:
            st.session_state.user = None
            st.rerun()

    st.markdown(
        '<div class="hero"><h1>Your money. Your goals.</h1>'
        '<p>One clear view of your finances, wherever life takes you.</p></div>',
        unsafe_allow_html=True,
    )

    st.sidebar.divider()
    st.sidebar.subheader("🌍 Reporting currency")
    report_currency = st.sidebar.selectbox(
        "Show dashboard totals in",
        CURRENCY_CODES,
        index=CURRENCY_CODES.index(st.session_state.get("report_currency", "INR")),
        format_func=lambda code: f"{CURRENCIES[code]['flag']} {code} — {CURRENCIES[code]['name']}",
        key="report_currency",
    )
    st.caption("Switch your reporting currency at any time. Original transaction amounts remain unchanged; dashboard equivalents use current exchange rates.")

    try:
        summary = get_financial_summary(user_id)
        usd_to_report, report_updated = get_rate("USD", report_currency)
        income = summary["income_usd"] * usd_to_report
        expenses = summary["expenses_usd"] * usd_to_report
        balance = summary["balance_usd"] * usd_to_report
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Total income · {report_currency}", fmt_money(income, report_currency))
        c2.metric(f"Total expenses · {report_currency}", fmt_money(expenses, report_currency))
        c3.metric(f"Available balance · {report_currency}", fmt_money(balance, report_currency))
        st.caption(f"Reporting rate: 1 USD = {usd_to_report:,.4f} {report_currency} · Updated: {report_updated} · Rates cached for up to 1 hour.")
    except Exception as error:
        st.error("Couldn't load reporting-currency totals. No estimated exchange rate has been substituted.")
        st.caption(str(error))
        return

    # Currency converter / rate comparison
    with st.expander("💱 Currency exchange centre", expanded=False):
        st.write("Compare currencies using the latest available exchange rate.")
        cc1, cc2, cc3 = st.columns([1, 1, 1.2])
        with cc1:
            from_currency = st.selectbox("From", CURRENCY_CODES, index=CURRENCY_CODES.index("INR"), key="converter_from")
        with cc2:
            to_currency = st.selectbox("To", CURRENCY_CODES, index=CURRENCY_CODES.index("USD"), key="converter_to")
        with cc3:
            convert_amount = st.number_input("Amount to convert", min_value=0.0, value=1000.0, step=100.0, key="converter_amount")
        try:
            conversion_rate, conversion_updated = get_rate(from_currency, to_currency)
            st.metric(
                f"Converted amount · {to_currency}",
                fmt_money(convert_amount * conversion_rate, to_currency),
                help="Calculated using the latest rate returned by the exchange-rate service.",
            )
            st.caption(f"1 {from_currency} = {conversion_rate:,.6f} {to_currency} · Updated: {conversion_updated}")
        except Exception as error:
            st.error("Couldn't fetch this exchange rate. Check your internet connection and try again.")
            st.caption(str(error))

    # Load the user's own transactions for charts and history.
    try:
        transactions = get_transactions(user_id)
    except Exception as error:
        st.error("Couldn't load transaction history.")
        st.caption(str(error))
        return

    st.divider()
    st.subheader("📊 Your money at a glance")
    if transactions.empty:
        st.info("Your charts will appear here after you save your first transaction.")
    else:
        data = transactions.copy()
        data["amount_usd"] = pd.to_numeric(data["amount_usd"], errors="coerce").fillna(0)
        data["type"] = data["type"].astype(str).str.lower()
        data["category"] = data["category"].fillna("Other").replace("", "Other")
        data["transaction_date"] = pd.to_datetime(data["transaction_date"], errors="coerce")
        data = data.dropna(subset=["transaction_date"])
        data["report_amount"] = data["amount_usd"] * usd_to_report

        left, right = st.columns(2)
        with left:
            st.markdown("#### Spending by category")
            spend = data[data["type"] == "expense"]
            if spend.empty:
                st.info("Add an expense to see the breakdown.")
            else:
                category_totals = spend.groupby("category", as_index=False)["report_amount"].sum()
                fig = px.pie(category_totals, names="category", values="report_amount", hole=0.62)
                fig.update_traces(textposition="inside", textinfo="percent+label", hovertemplate="%{label}<br>" + report_currency + " %{value:,.2f}<extra></extra>")
                fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), showlegend=False, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, use_container_width=True)
        with right:
            st.markdown("#### Monthly income vs expenses")
            data["Month"] = data["transaction_date"].dt.to_period("M").astype(str)
            monthly = data.groupby(["Month", "type"], as_index=False)["report_amount"].sum()
            monthly["Type"] = monthly["type"].map({"income": "Income", "expense": "Expenses"}).fillna(monthly["type"].str.title())
            fig = px.bar(monthly, x="Month", y="report_amount", color="Type", barmode="group", labels={"report_amount": report_currency, "Month": "Month"}, color_discrete_map={"Income": "#27834C", "Expenses": "#E28B68"})
            fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), legend_title_text="", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title=report_currency)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("➕ Add a transaction")
    transaction_type = st.radio("What would you like to record?", ["expense", "income"], horizontal=True, format_func=lambda value: "Expense" if value == "expense" else "Income", key="new_transaction_type")
    is_expense = transaction_type == "expense"
    currency = st.selectbox("Transaction currency", CURRENCY_CODES, index=CURRENCY_CODES.index("INR"), key="transaction_currency")
    try:
        usd_rate, rate_updated = get_rate(currency, "USD")
        st.caption(f"Live conversion: 1 {currency} = {usd_rate:.6f} USD · Updated: {rate_updated}")
        rate_error = None
    except Exception as error:
        usd_rate, rate_error = None, str(error)
        st.error("Couldn't fetch the current exchange rate. The transaction won't be saved with an invented rate.")

    with st.form("transaction_form", clear_on_submit=True):
        if is_expense:
            description = st.text_input("Description (optional)", placeholder="e.g. Groceries, transport")
            category = st.selectbox("Expense category", ["Food", "Transport", "Rent", "Shopping", "Education", "Bills", "Health", "Entertainment", "Other"])
        else:
            description = ""
            category = "Income"
            st.caption("Quick income entry: amount and date only.")
        amount = st.number_input("Amount", min_value=0.01, value=100.0, step=10.0)
        transaction_date = st.date_input("Transaction date", value=date.today())
        if usd_rate is not None:
            st.info(f"Estimated value: {fmt_money(amount, currency)} ≈ {fmt_money(amount * usd_rate, 'USD')} ≈ {fmt_money(amount * usd_rate * usd_to_report, report_currency)}")
        submitted = st.form_submit_button("Save transaction", type="primary", use_container_width=True)
        if submitted:
            if usd_rate is None:
                st.error("Transaction not saved because a reliable exchange rate is unavailable.")
            else:
                try:
                    add_transaction(user_id=user_id, transaction_date=transaction_date, transaction_type=transaction_type, description=description, category=category, amount=amount, currency=currency, exchange_rate_to_usd=usd_rate)
                    st.success("Transaction saved successfully!")
                    st.rerun()
                except Exception as error:
                    st.error("Couldn't save the transaction. Check the database connection and table schema.")
                    st.caption(str(error))

    st.divider()
    st.subheader("📋 Transaction history")
    if transactions.empty:
        st.info("No transactions yet.")
    else:
        display = transactions.copy()
        display["Date"] = display["transaction_date"]
        display["Type"] = display["type"].astype(str).str.title()
        display["Description"] = display["description"].fillna("")
        display["Category / source"] = display["category"].fillna("")
        display["Original amount"] = display.apply(lambda row: f"{row['currency']} {float(row['amount']):,.2f}", axis=1)
        display["USD equivalent"] = display["amount_usd"].apply(lambda value: fmt_money(value, "USD"))
        display[f"Equivalent · {report_currency}"] = display["amount_usd"].apply(lambda value: fmt_money(float(value) * usd_to_report, report_currency))
        st.dataframe(display[["Date", "Type", "Description", "Category / source", "Original amount", "USD equivalent", f"Equivalent · {report_currency}"]], use_container_width=True, hide_index=True)


st.sidebar.title("💚 FinanceBuddy")
st.sidebar.caption("Personal finance, simplified")
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.markdown('<div class="hero"><h1>Make every rupee count.</h1><p>Understand your spending, build better habits, and manage money across currencies.</p></div>', unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Log in", "Create account"])
    with login_tab:
        st.subheader("Welcome back")
        email = st.text_input("Email address", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Log in", type="primary", use_container_width=True):
            if not email.strip() or not password:
                st.error("Enter your email address and password.")
            else:
                try:
                    result = supabase.auth.sign_in_with_password({"email": email.strip(), "password": password})
                    st.session_state.user = result.user
                    st.rerun()
                except Exception:
                    st.error("Login failed. Check your email and password, and confirm your email if required.")
    with signup_tab:
        st.subheader("Create your account")
        full_name = st.text_input("Full name", key="signup_name")
        email = st.text_input("Email address", key="signup_email")
        password = st.text_input("Create a password", type="password", key="signup_password")
        confirm_password = st.text_input("Confirm password", type="password", key="confirm_password")
        if st.button("Create my account", type="primary", use_container_width=True):
            if not full_name.strip() or not email.strip() or not password:
                st.error("Please complete all fields.")
            elif password != confirm_password:
                st.error("Your passwords do not match.")
            elif len(password) < 8:
                st.error("Use a password with at least 8 characters.")
            else:
                try:
                    result = supabase.auth.sign_up({"email": email.strip(), "password": password, "options": {"data": {"full_name": full_name.strip()}}})
                    if result.user and result.session:
                        st.session_state.user = result.user
                        save_profile(result.user, full_name.strip())
                        st.success("Account created!")
                        st.rerun()
                    elif result.user:
                        st.success("Account created! Check your email for the verification link, then log in.")
                    else:
                        st.error("Signup could not be completed.")
                except Exception:
                    st.error("Signup failed. The email may already be registered, or the connection may be invalid.")
    st.caption("🔒 Your financial journey deserves privacy and security.")
else:
    show_dashboard()
