from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator

DisplayName = Annotated[str, Field(min_length=1, max_length=100)]


class UserBase(BaseModel):
    email: EmailStr
    display_name: DisplayName


class UserCreate(UserBase):
    password: SecretStr

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, password: SecretStr) -> SecretStr:
        length = len(password.get_secret_value())
        if not 8 <= length <= 128:
            raise ValueError("password must be between 8 and 128 characters")
        return password


class UserPublic(UserBase):
    id: UUID
    is_active: bool = True
    created_at: datetime


class UserInDB(UserPublic):
    password_hash: str
