from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.dependencies import Auth, FileServiceDep
from app.schema.files import CsvPreviewResponse, FilePageResponse

router = APIRouter(prefix="/api/files", tags=["Dosyalar"])


@router.get("", response_model=FilePageResponse)
def files(
    principal: Auth,
    service: FileServiceDep,
    path: Annotated[str, Query(max_length=1024)] = "",
    cursor: Annotated[str | None, Query(max_length=8192)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return service.list(principal, path, cursor, limit)


@router.get("/preview", response_model=CsvPreviewResponse)
def preview(
    principal: Auth,
    service: FileServiceDep,
    path: Annotated[str, Query(min_length=1, max_length=1024)],
):
    return service.preview(principal, path)


@router.get(
    "/download",
    response_model=None,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Orijinal dosya baytları; attachment olarak indirilir",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
def download(
    principal: Auth,
    service: FileServiceDep,
    path: Annotated[str, Query(min_length=1, max_length=1024)],
):
    result = service.download(principal, path)
    body = result["Body"]

    def chunks():
        try:
            while chunk := body.read(64 * 1024):
                yield chunk
        finally:
            body.close()

    # HTTP akışı/attachment API'nin sorumluluğudur; dosya RAM'e toplanmaz.
    return StreamingResponse(
        chunks(),
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(result["ContentLength"]),
            "Content-Disposition": "attachment; filename=download; "
            f"filename*=UTF-8''{quote(path.split('/')[-1], safe='')}",
        },
        background=BackgroundTask(body.close),
    )
