import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

PII_PATTERNS = [
    re.compile(r"[\w\.-]+@[\w\.-]+"),  # Email addresses
    re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"),  # SSN (very basic)
    re.compile(r"\b\d{16}\b"),  # Credit card (very basic)
]

REDACTION = "[REDACTED]"

def redact_pii(text: str) -> str:
    for pattern in PII_PATTERNS:
        text = pattern.sub(REDACTION, text)
    return text

class PIISanitizerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Redact PII in request body (if JSON)
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.body()
            try:
                import json
                data = json.loads(body)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, str):
                            data[k] = redact_pii(v)
                body = json.dumps(data).encode()
                request._body = body  # Patch the request body
            except Exception:
                pass
        response: Response = await call_next(request)
        # Redact PII in response (if JSON)
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                content = await response.body()
                import json
                data = json.loads(content)
                # Recursively redact all string values in the JSON
                def redact_all_strings(obj):
                    if isinstance(obj, str):
                        return redact_pii(obj)
                    elif isinstance(obj, dict):
                        return {k: redact_all_strings(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [redact_all_strings(i) for i in obj]
                    else:
                        return obj
                redacted_data = redact_all_strings(data)
                from fastapi.responses import JSONResponse
                response = JSONResponse(content=redacted_data, status_code=response.status_code, headers=dict(response.headers))
            except Exception:
                pass
        return response
