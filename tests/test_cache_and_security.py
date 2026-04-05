import pytest
from fastapi.testclient import TestClient
from app.main import app
import os
import time

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

def test_cache_exact_match(client):
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
        "stream": False
    }
    # First call: should be a cache miss (LLM or mock)
    response1 = client.post("/v1/chat/completions", json=payload)
    assert response1.status_code == 200
    # Second call: should be a cache hit (exact)
    response2 = client.post("/v1/chat/completions", json=payload)
    assert response2.status_code == 200
    # Check that the provider in metrics is 'cache_exact' (or similar)
    metrics = response2.headers.get("X-Gateway-Metrics", "")
    assert "cache_exact" in metrics or "cache" in metrics

def test_pii_redaction(client):
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "My email is alice@example.com and my SSN is 123-45-6789."}],
        "stream": False
    }
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    # The response body should not contain the email or SSN
    assert "alice@example.com" not in response.text
    assert "123-45-6789" not in response.text
    assert "[REDACTED]" in response.text
