import pytest
import streamlit.web.bootstrap
import threading
import time
import requests
import os

# Set up the backend URL for tests
gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000/v1/chat/completions")
ui_url = "http://localhost:8501"

@pytest.fixture(scope="session", autouse=True)
def launch_streamlit():
    # Launch Streamlit in a background thread
    def run():
        streamlit.web.bootstrap.run("main.py", "", [], {})
    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(5)  # Wait for UI to start
    yield
    # No teardown needed (daemon thread)

def test_gateway_responds():
    resp = requests.post(gateway_url, json={
        "model": "Penny Pincher",
        "messages": [{"role": "user", "content": "Hello!"}]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "choices" in data
    assert "metrics" in data


def test_ui_homepage():
    resp = requests.get(ui_url)
    assert resp.status_code == 200
    # Streamlit renders content dynamically; homepage text is not in raw HTML
    # This test only checks that the UI server is up
