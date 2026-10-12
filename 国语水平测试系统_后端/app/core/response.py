"""统一响应结构：{ code, message, data }。

与前端 api.request 的约定保持一致：
  code == 0    成功
  code == 401  未登录（前端跳登录页）
  code == 403  角色不符
  其他非 0     业务失败，message 直接展示给用户
"""
from typing import Any


def ok(data: Any = None, message: str = "success") -> dict:
    """成功响应。"""
    return {"code": 0, "message": message, "data": data}


def fail(code: int = 400, message: str = "请求有误") -> dict:
    """失败响应。"""
    return {"code": code, "message": message, "data": None}