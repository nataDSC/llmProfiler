import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_gateway_metrics_header_present():
    client = TestClient(app)
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [{"role": "user", "content": "Hello!"}],
        "stream": False
    }
    # The correct path is /v1/chat/completions due to router prefixing
    response = client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 200
    assert "X-Gateway-Metrics" in response.headers
    metrics = response.headers["X-Gateway-Metrics"]
    assert "latency" in metrics or "latency_ms" in metrics
