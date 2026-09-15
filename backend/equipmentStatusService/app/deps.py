# Auth seam: stub trusting the X-User-Id header today, real JWT verification
# lands here later (see docs/AUTH_INTEGRATION.md) without endpoint changes.
from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class User(BaseModel):
    id: str
    role: str


def get_current_user(x_user_id: str | None = Header(default=None)) -> User:
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Id header",
        )
    return User(id=x_user_id, role="technical_support")  # role stubbed
