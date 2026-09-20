from fastapi import HTTPException, status
from postgrest.exceptions import APIError

NOT_FOUND_ERRCODE = "P0002"


def rpc_error_to_http(exc: APIError) -> HTTPException:
    if exc.code == NOT_FOUND_ERRCODE:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Database operation failed",
    )
