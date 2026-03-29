from app.services.pricing import get_model_pricing

def test_get_model_pricing():
    price = get_model_pricing("openai", "gpt-3.5-turbo")
    assert price is not None
    assert price["input"] > 0
