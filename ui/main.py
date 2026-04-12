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
    "Anthropic Claude 2.1": ("anthropic", "claude-3-haiku-20240307"),
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

# --- Disable Cache Toggle ---
disable_cache = st.sidebar.toggle("Disable Cache (bypass)", value=False, help="Bypass cache for all requests (for rate limit/manual testing)")

if st.sidebar.button("Invalidate Cache"):
    # Call the backend endpoint to invalidate cache (correct path with prefix)
    ADMIN_URL = os.getenv("GATEWAY_ADMIN_URL", "http://gateway:8000/v1/chat/admin/invalidate_cache")
    try:
        resp = requests.post(ADMIN_URL, timeout=10)
        if resp.status_code == 200:
            st.sidebar.success("Cache invalidated!")
        else:
            st.sidebar.error(f"Failed to invalidate cache: {resp.text}")
    except Exception as e:
        st.sidebar.error(f"Error: {e}")

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
    st.text_area("Redacted LLM response", value=redacted_output, key="redacted_output", disabled=True)

# --- Backend URL config ---

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000/v1/chat/completions")

# --- Helper: Send chat request to backend ---
def send_chat_request(user_input, chaos_target):
    headers = {}
    if chaos_target and chaos_target.lower() != "none":
        headers["X-Simulate-Error"] = chaos_target.lower()
    if disable_cache:
        headers["X-Disable-Cache"] = "true"
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


# --- Main Input/Results Layout ---
col1, col2 = st.columns(2)

# --- Clear Button ---

def clear_all():
    # Explicitly clear user_input so text_area is reset
    st.session_state["user_input"] = ""
    for key in ["_last_content", "_trace_output", "_redacted_prompt", "_latest_result"]:
        if key in st.session_state:
            st.session_state.pop(key)

with col1:
    st.subheader("User Sent")
    if st.button("Clear", key="clear_button"):
        clear_all()
        st.rerun()
    user_input = st.text_area("Your message", key="user_input")
    # Show redacted prompt after sending
    if st.session_state.get("_redacted_prompt"):
        st.markdown(
            f"""
            <div style='background: #fff3cd; border-radius: 8px; padding: 1.2em; margin-top: 1em; border: 2px solid #bfa500;'>
                <span style='font-size: 1.1em; font-weight: bold; color: #bfa500;'>Redacted Prompt:</span><br><br>
                <span style='font-size: 1.05em; color: #222;'>{st.session_state['_redacted_prompt']}</span>
            </div>
            """,
            unsafe_allow_html=True
        )

# --- Metrics Dashboard Columns (define early so always available) ---
metrics_col1, metrics_col2, metrics_col3 = st.columns(3)

# with col2:
#     st.subheader("Gateway Received (PII Redacted)")
#     # Show redacted prompt after sending, always visible with results
#     redacted_prompt_to_show = st.session_state.get("_redacted_prompt", "")
#     if "_latest_result" in st.session_state and st.session_state["_latest_result"]:
#         latest_result = st.session_state["_latest_result"]
#         if "redacted_prompt" in latest_result and latest_result["redacted_prompt"]:
#             redacted_prompt_to_show = latest_result["redacted_prompt"]
#     if redacted_prompt_to_show:
#         st.markdown(
#             f"""
#             <div style='background: #fff3cd; border-radius: 8px; padding: 1.2em; margin-bottom: 1em; border: 2px solid #bfa500;'>
#                 <span style='font-size: 1.1em; font-weight: bold; color: #bfa500;'>Redacted Prompt (PII removed):</span><br><br>
#                 <span style='font-size: 1.05em; color: #222;'>{redacted_prompt_to_show}</span>
#             </div>
#             """,
#             unsafe_allow_html=True
#         )
#     st.text_area("Trace", value=st.session_state.get("_trace_output", ""), key="trace_output", disabled=True)
# --- Execution Trace Panel (moved up) ---
st.markdown("---")
st.header("Execution Trace")
trace_placeholder = st.empty()
trace_placeholder.info("[Trace will appear here after sending a request]")

# --- Send Button ---
if st.button("Send"):
    with st.spinner("Contacting Gateway..."):
        result = send_chat_request(user_input, chaos_target)
        # st.info(f"[DEBUG] Raw backend result: {result}")
        # st.info(f"[DEBUG] UI sees redacted_prompt: {result.get('redacted_prompt', None)}")

        # Show the redacted prompt immediately after sending
        # if result.get('redacted_prompt'):
        #     st.markdown(
        #         f"""
        #         <div style='background: #fff3cd; border-radius: 8px; padding: 1.2em; margin-bottom: 1em; border: 2px solid #bfa500;'>
        #             <span style='font-size: 1.1em; font-weight: bold; color: #bfa500;'>Redacted Prompt (PII removed):</span><br><br>
        #             <span style='font-size: 1.05em; color: #222;'>{result['redacted_prompt']}</span>
        #         </div>
        #         """,
        #         unsafe_allow_html=True
        #     )
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
            st.session_state["_redacted_prompt"] = result.get("redacted_prompt", "")
            st.session_state["_latest_result"] = result
            trace_placeholder.info(st.session_state["_trace_output"])
            metrics = result.get("metrics", {})
            # Display actual backend metrics
            cost = metrics.get("estimated_cost_usd", 0.0)
            latency = metrics.get("total_latency_ms", 0.0)
            tps = metrics.get("tokens_per_second", 0.0)
            metrics_col1.metric("Total Cost ($)", f"${cost:,.4f}")
            metrics_col2.metric("Latency (ms)", f"{latency:.0f} ms")
            metrics_col3.metric("Tokens/sec", f"{tps:.2f}")
            # Optionally clear session state after each query to avoid stale data
            # for key in ["_last_content", "_trace_output", "_redacted_prompt", "_latest_result"]:
            #     st.session_state.pop(key, None)
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
