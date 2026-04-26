from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

app = FastAPI(title="astro-api", version="0.1.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, "error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": code, "detail": str(exc.detail)},
        headers=exc.headers,
    )


_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
