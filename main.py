import uvicorn
from config.settings import get_settings


def main():
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
