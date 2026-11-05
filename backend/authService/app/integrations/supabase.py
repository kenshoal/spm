from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


def get_supabase_client() -> Client:
    """A fresh client per call, for sign-up and sign-in.

    ``sign_up`` and ``sign_in_with_password`` store the resulting session on
    the client, so sharing one would leak a user's session into other
    requests. Token verification uses ``get_supabase_verifier_client``.
    """
    settings = get_settings()
    return create_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_publishable_key.get_secret_value(),
    )


@lru_cache
def get_supabase_verifier_client() -> Client:
    """One shared client for ``auth.get_user(token)``.

    ``get_user`` is given the token explicitly and stores nothing on the
    client, so it is safe to share. Reusing it keeps the HTTPS connection to
    Supabase open instead of a new handshake on every /auth/me call.
    """
    return get_supabase_client()


@lru_cache
def get_supabase_admin_client() -> Client:
    """One shared service-role client (admin API and staff_roles reads).

    It never signs in, so it holds no per-user state. A missing secret key
    raises before anything is cached, so a later configuration still works.
    """
    settings = get_settings()
    if settings.supabase_secret_key is None:
        raise ValueError("SUPABASE_SECRET_KEY is not configured")
    return create_client(
        str(settings.supabase_url).rstrip("/"),
        settings.supabase_secret_key.get_secret_value(),
    )
