import math
import uuid
from contextvars import ContextVar
from typing import Any, Generic, TypeVar

from fastapi import HTTPException
from pydantic import BaseModel

T = TypeVar("T")

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class ErrorEntry(BaseModel):
    field: str | None = None
    code: str = ""
    message: str = ""


class ErrorDetails(BaseModel):
    error_message: str = ""
    error_errors: list[ErrorEntry] = []


class PaginationMeta(BaseModel):
    pagination_page: int | None = None
    pagination_limit: int | None = None
    pagination_offset: int | None = None
    pagination_total: int | None = None
    pagination_total_pages: int | None = None
    pagination_has_next: bool | None = None


class ApiResponse(BaseModel, Generic[T]):
    response_status: bool
    response_code: int
    response_message: str
    response_details: dict = {}
    response_request_id: str | None = None
    response_pagination: PaginationMeta | None = None
    response_data: T | None = None


def _rid() -> str:
    return request_id_ctx.get() or str(uuid.uuid4())


def ok(data: Any, *, message: str = "OK", code: int = 200) -> dict:
    return {
        "response_status": True,
        "response_code": code,
        "response_message": message,
        "response_details": {},
        "response_request_id": _rid(),
        "response_pagination": None,
        "response_data": data,
    }


def ok_list(
    items: list,
    *,
    total: int,
    limit: int,
    offset: int,
    message: str = "OK",
) -> dict:
    page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    has_next = (offset + limit) < total
    return {
        "response_status": True,
        "response_code": 200,
        "response_message": message,
        "response_details": {},
        "response_request_id": _rid(),
        "response_pagination": {
            "pagination_page": page,
            "pagination_limit": limit,
            "pagination_offset": offset,
            "pagination_total": total,
            "pagination_total_pages": total_pages,
            "pagination_has_next": has_next,
        },
        "response_data": items,
    }


class AppError(HTTPException):
    def __init__(
        self,
        status_code: int,
        response_message: str,
        *,
        error_message: str = "",
        error_errors: list[dict] | None = None,
    ):
        super().__init__(status_code=status_code, detail=response_message)
        self.response_message = response_message
        self.error_message = error_message or response_message
        self.error_errors = error_errors or []


def fail(
    code: int,
    message: str,
    *,
    error_message: str = "",
    errors: list[dict] | None = None,
) -> dict:
    return {
        "response_status": False,
        "response_code": code,
        "response_message": message,
        "response_details": {
            "error_message": error_message or message,
            "error_errors": errors or [],
        },
        "response_request_id": _rid(),
        "response_pagination": None,
        "response_data": None,
    }
