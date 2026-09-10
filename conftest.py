# Test environment: auth.py fails closed without TOKENS, so seed one for router imports.
import os
os.environ.setdefault("TOKENS", "test-token")
