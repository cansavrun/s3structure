import json
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ErrorKind, ServiceError
from app.schema.error import ErrorResponse

logger = logging.getLogger("tenantfiles")

# Alt katmanlar HTTP durum kodunu bilmez; eşleme yalnızca HTTP adapter'ındadır.
ERROR_STATUS = {
    ErrorKind.INVALID_INPUT: 400,
    ErrorKind.UNAUTHENTICATED: 401,
    ErrorKind.FORBIDDEN: 403,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.CONFLICT: 409,
    ErrorKind.TOO_LARGE: 413,
    ErrorKind.UNSUPPORTED: 415,
    ErrorKind.INVALID_DATA: 422,
    ErrorKind.RATE_LIMITED: 429,
    ErrorKind.UNAVAILABLE: 503,
}


async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
    return JSONResponse(
        status_code=ERROR_STATUS[exc.kind],
        content=ErrorResponse(detail=exc.message).model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def validation_error(request, exc):
    # Pydantic'in varsayılan `input` alanı login sırrını geri yansıtabilir.
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            detail="İstek alanları geçersiz", request_id=request.state.request_id
        ).model_dump(mode="json"),
    )


async def response_validation_error(request, exc):
    # Bu bir sunucu hatasıdır (500), kullanıcının isteğinin hatası (422) değildir.
    # exc/body/errors() iç veri içerebilir; cevapta veya logda göstermeyiz.
    logger.error(json.dumps({"event": "invalid_response", "request_id": request.state.request_id}))
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail="Sunucu yanıtı oluşturulamadı", request_id=request.state.request_id
        ).model_dump(mode="json"),
    )


async def database_error(request, exc):
    logger.error(
        json.dumps({"event": "database_unavailable", "request_id": request.state.request_id})
    )
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(detail="Veritabanına ulaşılamıyor").model_dump(
            mode="json", exclude_none=True
        ),
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, service_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ResponseValidationError, response_validation_error)
    app.add_exception_handler(SQLAlchemyError, database_error)
