from app.repositories import InMemoryUserRepository, UserRepository

user_repository = InMemoryUserRepository()


def get_user_repository() -> UserRepository:
    return user_repository
