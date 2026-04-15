import re
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


# Enhanced PII regex patterns
PII_PATTERNS = [
    # Email addresses
    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    # SSN (US Social Security Number)
    re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b"),
    # Credit card numbers (Visa, MasterCard, Amex, Discover, generic 16-digit)
    re.compile(r"(?:\b\d{4}[- ]?){3}\d{4}\b"),
    # Phone numbers (US, various formats)
    re.compile(r"\(?\b\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    # Addresses (simple US street address patterns)
    re.compile(r"\b\d{1,6}\s+[A-Za-z0-9.,'\-\s]+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Suite|Apt|Apartment|Unit)\b[\w\s,.'-]*"),
]

REDACTION = "[REDACTED]"


def redact_pii(text: str) -> str:
    for pattern in PII_PATTERNS:
        text = pattern.sub(REDACTION, text)
    return text

# Recursively redact all string values in a nested structure
def redact_all_strings(obj):
    if isinstance(obj, str):
        return redact_pii(obj)
    elif isinstance(obj, dict):
        return {k: redact_all_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [redact_all_strings(i) for i in obj]
    elif isinstance(obj, tuple):
        return tuple(redact_all_strings(i) for i in obj)
    else:
        return obj

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
                    elif isinstance(obj, tuple):
                        return tuple(redact_all_strings(i) for i in obj)
                    else:
                        return obj
                redacted_data = redact_all_strings(data)
                from fastapi.responses import JSONResponse
                return JSONResponse(content=redacted_data, status_code=response.status_code, headers=dict(response.headers))
            except Exception:
                pass
        return response
