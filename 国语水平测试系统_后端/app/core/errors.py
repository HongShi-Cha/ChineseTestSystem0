"""业务异常 + 全局异常处理。

所有异常都被转成 { code, message, data } 结构返回，
HTTP 状态码统一为 200，前端只解析 body.code —— 与 Java 版行为一致。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class BizException(Exception):
    """业务异常：账号密码错误、账号已存在等"预期内的错误"。"""

    def __init__(self, message: str = "请求有误", code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _payload(code: int, message: str) -> dict:
    return {"code": code, "message": message, "data": None}


def register_exception_handlers(app: FastAPI) -> None:
    """把全局异常处理器挂到 FastAPI 实例上。"""

    @app.exception_handler(BizException)
    async def _handle_biz(request: Request, exc: BizException):
        return JSONResponse(status_code=200, content=_payload(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):
        first = (exc.errors() or [{}])[0]
        loc = ".".join(str(x) for x in first.get("loc", ()) if x not in ("body", "query"))
        msg = first.get("msg", "参数校验失败")
        return JSONResponse(status_code=200, content=_payload(400, f"{loc} {msg}".strip()))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):
        # 404 之类的框架错误也包装成统一结构，方便前端统一处理
        message = "接口不存在" if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(status_code=200, content=_payload(exc.status_code, message))

    @app.exception_handler(Exception)
    async def _handle_any(request: Request, exc: Exception):
        logger.exception("系统异常: %s", exc)
        return JSONResponse(status_code=200, content=_payload(500, "系统繁忙，请稍后重试"))