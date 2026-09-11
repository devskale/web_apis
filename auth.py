import os
import secrets
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from dotenv import load_dotenv

load_dotenv()

# Use auto_error=False so a missing header becomes our own 401 response.
security = HTTPBearer(auto_error=False)

# Fail closed: without a usable TOKENS value the app must not start with auth
# silently disabled. An empty/whitespace TOKENS value is a misconfiguration,
# not a bypass.
tokens_str = os.getenv('TOKENS')
if tokens_str is None or not tokens_str.strip():
    raise ValueError("TOKENS environment variable not set or empty")

valid_tokens = {token.strip()
                for token in tokens_str.split(',') if token.strip()}
if not valid_tokens:
    raise ValueError("TOKENS environment variable contains no usable tokens")

# Never log the token values themselves - only the count.
print(f"Loaded {len(valid_tokens)} valid tokens")


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials (GET /help for usage)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    # Constant-time comparison so response timing doesn't leak how much of a
    # prefix matched.
    if not any(secrets.compare_digest(token, valid) for valid in valid_tokens):
        raise HTTPException(
            status_code=401,
            detail="Invalid token (GET /help for usage)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token
