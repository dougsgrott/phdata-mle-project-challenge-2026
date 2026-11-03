"""Sound Realty price estimate: a small Streamlit front end for the price API.

Configuration (environment variables):
  API_URL      Base URL of the API, e.g. http://localhost:8000 or the AWS stage URL
  API_KEY      Sent as the x-api-key header when set (needed for the AWS API only)
  UI_PASSWORD  When set, the page asks for it first; when unset, there is no gate
"""

import hmac
import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("API_KEY")
UI_PASSWORD = os.environ.get("UI_PASSWORD")
TIMEOUT_SECONDS = 35  # the first request after a quiet period can take ~10 s on AWS

st.set_page_config(page_title="Sound Realty price estimate")


def password_gate() -> None:
    """Stop the page until the right password is entered (once per browser session)."""
    if not UI_PASSWORD or st.session_state.get("authenticated"):
        return
    st.title("Sound Realty price estimate")
    password = st.text_input("Password", type="password")
    if password:
        if hmac.compare_digest(password, UI_PASSWORD):
            st.session_state["authenticated"] = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()


def error_message(response: httpx.Response) -> str:
    """Turn an API error response into one readable sentence."""
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, list):  # validation errors: one message per field
        return "; ".join(item.get("msg", str(item)) for item in detail)
    if detail:
        return str(detail)
    if response.status_code == 403:
        return "The API rejected the request: the API key is missing or wrong."
    return f"The API returned an error (HTTP {response.status_code})."


password_gate()

st.title("Sound Realty price estimate")
st.write(
    "Enter what you know about the house. Leave a field empty if you don't know it: "
    "the estimate fills it in from similar houses. The zipcode is required."
)

with st.form("house"):
    zipcode = st.text_input("Zipcode", placeholder="98125")
    col1, col2 = st.columns(2)
    with col1:
        bedrooms = st.number_input("Bedrooms", min_value=-10, step=1, value=None)
        bathrooms = st.number_input("Bathrooms", min_value=0.0, step=0.25, value=None)
        floors = st.number_input("Floors", min_value=0.0, step=0.5, value=None)
        sqft_lot = st.number_input(
            "Lot size (sq ft)", min_value=0.0, step=100.0, value=None
        )
    with col2:
        sqft_living = st.number_input(
            "Living area (sq ft)", min_value=0.0, step=50.0, value=None
        )
        sqft_above = st.number_input(
            "Area above ground (sq ft)", min_value=0.0, step=50.0, value=None
        )
        sqft_basement = st.number_input(
            "Basement area (sq ft)", min_value=0.0, step=50.0, value=None
        )
    submitted = st.form_submit_button("Estimate price")

if submitted:
    if not zipcode.strip():
        st.error("Please enter a zipcode.")
        st.stop()

    house = {
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "sqft_living": sqft_living,
        "sqft_lot": sqft_lot,
        "floors": floors,
        "sqft_above": sqft_above,
        "sqft_basement": sqft_basement,
        "zipcode": zipcode.strip(),
    }
    headers = {"x-api-key": API_KEY} if API_KEY else {}

    try:
        with st.spinner("Estimating..."):
            response = httpx.post(
                f"{API_URL}/predict",
                json=house,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )
    except httpx.HTTPError:
        st.error("Could not reach the price service. Please try again in a moment.")
        st.stop()

    if response.status_code != 200:
        st.error(error_message(response))
        st.stop()

    result = response.json()
    st.metric("Estimated price", f"${result['predicted_price']:,.0f}")

    filled = result.get("imputed_fields", {})
    if filled:
        st.caption(
            "Estimated from similar houses: "
            + ", ".join(
                f"{field.replace('_', ' ')} {value:,.2f}"
                for field, value in filled.items()
            )
        )
