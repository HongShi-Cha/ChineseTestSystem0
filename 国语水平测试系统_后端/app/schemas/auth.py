"""登录 / 注册请求体。"""
from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50, description="学号或管理员账号")
    password: str = Field(min_length=1, max_length=64)


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    student_no: str = Field(min_length=1, max_length=30)
    class_name: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=6, max_length=20)

    @property
    def username(self) -> str:
        """注册时用学号作为登录账号。"""
        return self.student_no