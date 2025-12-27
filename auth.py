import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from dotenv import load_dotenv

load_dotenv()

security = HTTPBearer()

# Load tokens from environment variables
tokens_str = os.getenv('TOKENS')
if not tokens_str:
    # It might be better to log a warning or raise an error depending on strictness
    # For now, we'll keep the behavior consistent with main.py
    # But since this is a module, raising ValueError at import time might crash the app if env not set
    # Let's assume it's set or handle it gracefully. 
    # main.py raised ValueError, so we will too.
    raise ValueError("TOKENS environment variable not set")

valid_tokens = {token.strip() for token in tokens_str.split(',')}
# For debugging
print(f"Loaded {len(valid_tokens)} valid tokens {valid_tokens}")


def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    print(f"Received token: {token}")  # Debugging line: print the token
    if token not in valid_tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
