import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from config import SUPABASE_URL, ADMIN_EMAILS

# Supabase now signs session tokens with an asymmetric key (ES256) rather than a shared
# HS256 secret, so verification uses the project's public JWKS instead of
# SUPABASE_JWT_SECRET. PyJWKClient caches fetched keys and looks one up by the token's kid.
_jwks_client = PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")


def decode_token(authorization: str = Header(...)) -> dict:
    """
    Verifies the Supabase-issued JWT and returns its full decoded payload. Shared by every
    route that needs to know who's asking - both the regular per-user routes and the
    admin-only routes build on this same verification step, so there's one place that
    checks a token is genuine rather than two copies that could drift apart.
    """
    token = authorization.replace("Bearer ", "")
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token, signing_key.key, algorithms=["ES256"], audience="authenticated"
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


def get_user_id_from_token(authorization: str = Header(...)) -> str:
    """
    Returns the user id the token was issued for. This is what lets the API act on behalf
    of 'whoever is currently logged in' without the frontend ever sending a user_id
    directly - the user_id always comes from a verified token, not from a form field a
    client could tamper with.
    """
    return decode_token(authorization)["sub"]


def require_admin(authorization: str = Header(...)) -> str:
    """
    Demo-grade admin check: an email allowlist from ADMIN_EMAILS, not a real roles system.
    Good enough to gate a portfolio demo's admin page behind something - NOT how you'd do
    this in production, where "admin" would be a role stored in the database and checked
    against a roles table, not a hardcoded env var comparison.
    """
    payload = decode_token(authorization)
    email = (payload.get("email") or "").lower()
    admin_emails = [e.strip().lower() for e in (ADMIN_EMAILS or "").split(",") if e.strip()]
    if not email or email not in admin_emails:
        raise HTTPException(status_code=403, detail="Admin access only")
    return payload["sub"]
