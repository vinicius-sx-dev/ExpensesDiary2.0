import logging
import traceback

import anyio
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth import router as auth
from app.config import settings
from app.finance import router as finance
from app.reports import router as reports
from app.security import limit
from app.statement_imports import router as statement_imports

logger = logging.getLogger("expenses_diary")

app = FastAPI(
    title="ExpensesDiary",
    version="2.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)



# Enforce actual streamed body size, not just the untrusted Content-Length header.
class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        # Upload route authenticates and acquires a shared lease BEFORE reading the body.
        if scope.get("path") == "/imports/preview" and scope.get("method") == "POST":
            return await self.app(scope, receive, send)
        body = bytearray()
        try:
            # A total deadline prevents an endless trickle of sub-limit/empty chunks.
            with anyio.fail_after(10):
                while True:
                    msg = await receive()
                    if msg["type"] == "http.disconnect":
                        return
                    chunk = msg.get("body", b"")
                    if len(body) + len(chunk) > 16384:
                        return await JSONResponse(
                            {"detail": "Requisição muito grande"}, status_code=413
                        )(scope, receive, send)
                    body.extend(chunk)
                    if not msg.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse(
                {"detail": "Tempo limite para receber a requisição"}, status_code=408
            )(scope, receive, send)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BodyLimit)


@app.middleware("http")
async def guard(request: Request, call_next):
    try:
        from starlette.concurrency import run_in_threadpool

        await run_in_threadpool(
            limit, "ip", request.client.host if request.client else "unknown", 300, 60
        )
        response = await call_next(request)
    except HTTPException as e:
        response = JSONResponse({"detail": e.detail}, status_code=e.status_code, headers=e.headers)
    except Exception as exc:
        # Log route, method, exception type and traceback frames without request data.
        logger.error(
            "Unhandled API error method=%s path=%s type=%s\\n%s",
            request.method,
            request.scope.get("route").path if request.scope.get("route") else "<unmatched>",
            type(exc).__name__,
            "".join(traceback.format_tb(exc.__traceback__)),
        )
        response = JSONResponse(
            {"detail": "Erro interno. Tente novamente mais tarde."}, status_code=500
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def validation(request, exc):
    # Never echo raw rejected input (passwords, OTPs, tokens).
    return JSONResponse(
        {
            "detail": "Dados inválidos",
            "fields": [
                {"field": ".".join(map(str, e["loc"])), "type": e["type"]} for e in exc.errors()
            ],
        },
        status_code=422,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    return JSONResponse({"detail": "Serviço temporariamente indisponível"}, status_code=503)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth)
app.include_router(finance)
app.include_router(reports)
app.include_router(statement_imports)

from app.pluggy import router as pluggy
app.include_router(pluggy)
from app.advisor.routes import router as advisor
app.include_router(advisor)


# Outer validation rejects invalid hosts before database-backed request limits.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    expose_headers=["Retry-After", "X-Error-Code"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Device-ID"],
)
