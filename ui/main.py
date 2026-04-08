import streamlit as st
import pandas as pd
import os
import requests

st.set_page_config(page_title="LLM Gateway & Profiler Demo", layout="wide")

# --- Sidebar: Policy Engine & Debug Tools ---
st.sidebar.title("Policy Engine & Debug Tools")
policy = st.sidebar.selectbox(
    "Routing Policy",
    ["Penny Pincher", "Speed Demon", "High Fidelity", "Chaos Mode"],
    help="Choose how the gateway routes your request."
)
chaos_target = st.sidebar.selectbox(
    "Simulate Failure",
    ["None", "OpenAI", "Anthropic"],
    help="Inject a simulated provider failure for demo purposes."
)
st.sidebar.markdown("---")
st.sidebar.header("Admin Panel")
if st.sidebar.button("Invalidate Cache"):
    st.session_state["invalidate_cache"] = True
    st.sidebar.success("Cache invalidation requested.")

# --- Theme Switcher Gadget ---
theme = st.sidebar.radio(
    "Theme",
    ["System", "Light", "Dark"],
    index=0,
    help="Switch between light, dark, or system theme."
)

# Inject theme CSS (Streamlit does not support theme switching at runtime, so this is a workaround)
if theme == "Light":
    st.markdown(
        """
        <style>
        body, .stApp { background-color: #fff !important; color: #222 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
elif theme == "Dark":
    st.markdown(
        """
        <style>
        body, .stApp { background-color: #18191A !important; color: #FAFAFA !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
# System: do nothing (use browser/OS default)

# --- Backend URL config ---
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000/v1/chat/completions")

# --- Helper: Send chat request to backend ---
def send_chat_request(user_input, policy, chaos_target):
    headers = {}
    if chaos_target and chaos_target.lower() != "none":
        headers["X-Simulate-Error"] = chaos_target.lower()
    # Example payload, adjust as needed for your backend
    payload = {
        "model": policy,  # This could be mapped to a real model/policy
        "messages": [{"role": "user", "content": user_input}],
    }
    try:
        resp = requests.post(GATEWAY_URL, json=payload, headers=headers, timeout=15)
        if resp.status_code == 429:
            return {"rate_limited": True}
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# --- Main Layout ---
st.title("LLM Gateway & Profiler Demo")

col1, col2 = st.columns(2)

with col1:
    st.subheader("User Sent")
    user_input = st.text_area("Your message", key="user_input")
with col2:
    st.subheader("Gateway Received (PII Redacted)")
    # Placeholder for redacted text
    st.text_area("Redacted message", value="", key="redacted_output", disabled=True)

# --- Send Button ---
if st.button("Send"):
    with st.spinner("Contacting Gateway..."):
        result = send_chat_request(user_input, policy, chaos_target)
        if result.get("rate_limited"):
            st.warning("429: Too many requests. Slow down.")
        elif result.get("error"):
            st.error(f"Error: {result['error']}")
        else:
            # Update UI with backend response
            redacted = result.get("redacted", "[No redacted output]")
            st.session_state["redacted_output"] = redacted
            trace = result.get("trace", "[No trace]")
            trace_placeholder.info(trace)
            metrics = result.get("metrics", {})
            metrics_col1.metric("Total Savings ($)", metrics.get("savings", "$0.00"))
            metrics_col2.metric("Latency Delta", metrics.get("latency_delta", "0 ms"))
            metrics_col3.metric("Cache Efficiency", metrics.get("cache_efficiency", "0%"))
            if result.get("pii_blocked"):
                st.info("PII Blocked: Sensitive data was detected and redacted.")

# --- Execution Trace Panel ---
st.markdown("---")
st.header("Execution Trace")
trace_placeholder = st.empty()
trace_placeholder.info("[Trace will appear here after sending a request]")

# --- Metrics Dashboard ---
st.markdown("---")
st.header("Metrics Dashboard")
metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
with metrics_col1:
    st.metric("Total Savings ($)", "$0.00")
with metrics_col2:
    st.metric("Latency Delta", "0 ms")
with metrics_col3:
    st.metric("Cache Efficiency", "0%")
st.caption("Pie chart and real metrics will appear here once backend is connected.")

# --- Rate Limiting & PII Badge ---
if False:  # Placeholder for rate limit/PII feedback
    st.warning("429: Too many requests. Slow down.")
    st.info("PII Blocked: <EMAIL> detected and redacted.")
