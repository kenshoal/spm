from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_user_repository
from app.models import UserCreate, UserPublic
from app.repositories import DuplicateEmailError, UserRepository

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register_user(
    user: UserCreate,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserPublic:
    try:
        stored_user = repository.create(user)
    except DuplicateEmailError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from error

    return UserPublic(
        id=stored_user.id,
        email=stored_user.email,
        display_name=stored_user.display_name,
        is_active=stored_user.is_active,
        created_at=stored_user.created_at,
    )
