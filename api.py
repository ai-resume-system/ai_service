import os

from dotenv import load_dotenv
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from resume_analyzer import analyze_resume_text
from schemas import AnalyzeCvRequest, AnalyzeCvResponse

load_dotenv()


async def health(_: Request):
    return JSONResponse({"status": True, "service": "ai_service"})


async def analyze_cv(request: Request):
    expected_key = os.getenv("AI_SERVICE_API_KEY", "").strip()
    request_key = request.headers.get("x-internal-api-key", "").strip()
    if expected_key and request_key != expected_key:
        return JSONResponse(
            {"code": 401, "message": "Invalid internal API key"},
            status_code=401,
        )

    try:
        payload = AnalyzeCvRequest.model_validate(await request.json())
    except ValidationError as exc:
        return JSONResponse(
            {"code": 400, "message": "Invalid request", "errors": exc.errors()},
            status_code=400,
        )

    try:
        analysis = await run_in_threadpool(
            analyze_resume_text,
            payload,
        )
        response = AnalyzeCvResponse(data=analysis)
        return JSONResponse(response.model_dump(mode="json"))
    except Exception as exc:
        return JSONResponse(
            {"code": 503, "message": "AI analysis failed", "details": str(exc)},
            status_code=503,
        )


app = Starlette(
    debug=False,
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/internal/cv/analyze", analyze_cv, methods=["POST"]),
    ],
)
