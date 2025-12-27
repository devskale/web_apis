import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from dotenv import load_dotenv

load_dotenv()

# Use auto_error=False to allow handling missing tokens manually (e.g., for testing bypass)
security = HTTPBearer(auto_error=False)

# Load tokens from environment variables
tokens_str = os.getenv('TOKENS')

# Check for testing/bypass keywords
# If TOKENS is explicitly set to "" (empty string) or "test", we bypass authentication.
# os.getenv returns None if variable is missing, but "" if set to empty.
# However, the previous logic raised ValueError if "not tokens_str" (which covers None and "").
# We need to distinguish between "missing" (None) and "empty/test" (Bypass).

bypass_auth = False
valid_tokens = set()

if tokens_str is None:
    raise ValueError("TOKENS environment variable not set")

# Parse tokens first
valid_tokens = {token.strip()
                for token in tokens_str.split(',')} if tokens_str else set()

# Check for bypass conditions:
# 1. TOKENS is empty string
# 2. "test" is in the list of tokens
if tokens_str == "" or "test" in valid_tokens:
    bypass_auth = True
    print("Auth bypassed: TOKENS is empty or contains 'test' - Accepting any or no token.")
else:
    print(f"Loaded {len(valid_tokens)} valid tokens {valid_tokens}")


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if bypass_auth:
        # If auth is bypassed, return a dummy token if none provided, or the provided one.
        if credentials:
            return credentials.credentials
        return "bypass-token"

    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    # print(f"Received token: {token}")  # Debugging line: print the token
    if token not in valid_tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
