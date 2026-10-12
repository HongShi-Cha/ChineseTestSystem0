"""题库增改请求体。"""
from pydantic import BaseModel, Field

from app.core.constants import DIFFICULTIES


class QuestionIn(BaseModel):
    type: int = Field(ge=1, le=4, description="1读单字 2读词语 3朗读短文 4命题说话")
    content: str = Field(min_length=1, description="题目内容")
    answer: str = Field(default="", description="拼音或参考答案")
    difficulty: str = Field(default="简单", description="简单/中等/困难")

    def normalized(self) -> dict:
        """规整字段：难度只允许三个取值，其余一律归到"简单"。"""
        difficulty = self.difficulty if self.difficulty in DIFFICULTIES else "简单"
        return {
            "type": self.type,
            "content": self.content.strip(),
            "answer": (self.answer or "").strip(),
            "difficulty": difficulty,
        }