import os
import pytest
from dotenv import load_dotenv

@pytest.fixture(scope="session", autouse=True)
def load_env():
    # Load .env file before any tests run
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"), override=True)
