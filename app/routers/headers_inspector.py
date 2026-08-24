from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user
from app.http_inspection import (
    BlockedUrlError,
    ConnectionFailedError,
    HeaderInspectionError,
    InvalidUrlError,
    RequestTimedOutError,
    TooManyRedirectsError,
    inspect_headers,
)
from app.schemas import HeaderInspectionRequest, HeaderInspectionResponse

router = APIRouter(prefix="/headers-inspector", tags=["headers-inspector"])

# Every other router in this service returns a plain-string `detail` for
# errors, since the frontend only ever displays it as-is. This endpoint's
# frontend tool switches on a machine-readable error code to pick a fixed
# i18n string (the convention every other DevHub tool already follows for
# validation errors) rather than displaying backend text — so `detail` here
# is a {code, message} object instead of a string.
_ERROR_STATUS_CODES: dict[type[HeaderInspectionError], int] = {
    InvalidUrlError: status.HTTP_400_BAD_REQUEST,
    BlockedUrlError: status.HTTP_400_BAD_REQUEST,
    ConnectionFailedError: status.HTTP_502_BAD_GATEWAY,
    RequestTimedOutError: status.HTTP_504_GATEWAY_TIMEOUT,
    TooManyRedirectsError: status.HTTP_502_BAD_GATEWAY,
}


@router.post("/inspect", response_model=HeaderInspectionResponse)
def inspect(
    payload: HeaderInspectionRequest, current_user: dict = Depends(get_current_user)
):
    try:
        result = inspect_headers(payload.url)
    except HeaderInspectionError as exc:
        raise HTTPException(
            status_code=_ERROR_STATUS_CODES.get(type(exc), status.HTTP_502_BAD_GATEWAY),
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return HeaderInspectionResponse(
        status_code=result.status_code,
        reason_phrase=result.reason_phrase,
        headers=[{"name": name, "value": value} for name, value in result.headers],
        final_url=result.final_url,
        redirect_count=result.redirect_count,
        duration_ms=result.duration_ms,
        http_version=result.http_version,
    )
