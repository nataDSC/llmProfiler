import streamlit as st
import pandas as pd
import os
import requests

st.set_page_config(page_title="LLM Gateway & Profiler Demo", layout="wide")

# --- Sidebar: Policy Engine & Debug Tools ---
st.sidebar.title("Policy Engine & Debug Tools")

# Map user-friendly policies to real provider/model pairs
POLICY_MODEL_MAP = {
    "Penny Pincher (gpt-3.5-turbo)": ("openai", "gpt-3.5-turbo"),
    "High Fidelity (gpt-4)": ("openai", "gpt-4"),
    "Anthropic Claude 2.1": ("anthropic", "claude-2.1"),
    "Chaos Mode (gpt-3.5-turbo)": ("openai", "gpt-3.5-turbo"),
}
policy_label = st.sidebar.selectbox(
    "Routing Policy",
    list(POLICY_MODEL_MAP.keys()),
    help="Choose how the gateway routes your request."
)
selected_provider, selected_model = POLICY_MODEL_MAP[policy_label]
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
                redacted_output = result.get("redacted", "[No redacted output]")
                trace = result.get("trace", "[No trace]")
                trace_placeholder.info(trace)
                metrics = result.get("metrics", {})
                metrics_col1.metric("Total Savings ($)", metrics.get("savings", "$0.00"))
                metrics_col2.metric("Latency Delta", metrics.get("latency_delta", "0 ms"))
                metrics_col3.metric("Cache Efficiency", metrics.get("cache_efficiency", "0%"))
                if result.get("pii_blocked"):
                    st.info("PII Blocked: Sensitive data was detected and redacted.")
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
    st.text_area("Redacted message", value=redacted_output, key="redacted_output", disabled=True)

# --- Backend URL config ---

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000/v1/chat/completions")

# --- Helper: Send chat request to backend ---
def send_chat_request(user_input, chaos_target):
    headers = {}
    if chaos_target and chaos_target.lower() != "none":
        headers["X-Simulate-Error"] = chaos_target.lower()
    # Use selected_provider and selected_model from sidebar
    payload = {
        "model": selected_model,
        "messages": [{"role": "user", "content": user_input}],
        "provider_hint": selected_provider,
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

# --- Metrics Dashboard Columns (define early so always available) ---
metrics_col1, metrics_col2, metrics_col3 = st.columns(3)

with col1:
    st.subheader("User Sent")
    user_input = st.text_area("Your message", key="user_input")
with col2:
    st.subheader("Gateway Received (PII Redacted)")
    # The redacted message will be rendered after sending, see below.
    st.text_area("Trace", value=st.session_state.get("_trace_output", ""), key="trace_output", disabled=True)
# --- Execution Trace Panel (moved up) ---
st.markdown("---")
st.header("Execution Trace")
trace_placeholder = st.empty()
trace_placeholder.info("[Trace will appear here after sending a request]")

# --- Send Button ---
if st.button("Send"):
    with st.spinner("Contacting Gateway..."):
        result = send_chat_request(user_input, chaos_target)
        st.info(f"[DEBUG] Raw backend result: {result}")
        if result.get("rate_limited"):
            st.warning("429: Too many requests. Slow down.")
        elif result.get("error"):
            st.error(f"Error: {result['error']}")
        else:
            # Update UI with backend response
            # Handle both direct and cached response structures
            content = None
            if "choices" in result and result["choices"]:
                content = result["choices"][0].get("message", {}).get("content")
            if not content:
                content = result.get("redacted", "[No redacted output]")
            st.session_state["_last_content"] = content
            st.session_state["_trace_output"] = result.get("trace", "[No trace]")
            trace_placeholder.info(st.session_state["_trace_output"])
            metrics = result.get("metrics", {})
            metrics_col1.metric("Total Savings ($)", metrics.get("savings", "$0.00"))
            metrics_col2.metric("Latency Delta", metrics.get("latency_delta", "0 ms"))
            metrics_col3.metric("Cache Efficiency", metrics.get("cache_efficiency", "0%"))
            if result.get("pii_blocked"):
                st.info("PII Blocked: Sensitive data was detected and redacted.")

            # Show the redacted message (styled)
            st.markdown(
                f"""
                <div style='background: #f5f5dc; border-radius: 8px; padding: 1.5em; margin-top: 1em; border: 2px solid #bfa500;'>
                    <span style='font-size: 1.3em; font-weight: bold; color: #bfa500;'>Redacted message:</span><br><br>
                    <span style='font-size: 1.15em; color: #222;'>{content}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

            # Show the actual LLM response (if available)
            actual_response = result.get("llm_response") or result["choices"][0]["message"].get("original_content") if "choices" in result and result["choices"] and "original_content" in result["choices"][0]["message"] else None
            if not actual_response:
                # Fallback: If no explicit original_content, use the same as redacted (for echo/test adapters)
                actual_response = result["choices"][0]["message"].get("content") if "choices" in result and result["choices"] else None

            if actual_response:
                st.markdown(
                    f"""
                    <div style='background: #e3f2fd; border-radius: 8px; padding: 1.5em; margin-top: 1em; border: 2px solid #1976d2;'>
                        <span style='font-size: 1.3em; font-weight: bold; color: #1976d2;'>Actual LLM response:</span><br><br>
                        <span style='font-size: 1.15em; color: #222;'>{actual_response}</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# --- Metrics Dashboard ---
st.markdown("---")
st.header("Metrics Dashboard")
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
