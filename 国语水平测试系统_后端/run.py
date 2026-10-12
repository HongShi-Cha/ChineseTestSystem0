"""开发启动脚本：python run.py

等价于：uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
"""
import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level="info",
    )