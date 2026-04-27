import json
import sys
import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from astro_api.auth import require_api_key
from astro_api.charts import DateOutOfRange, build_natal, build_sky, build_synastry, build_transits
from astro_api.charts import ResolvedLocation as ChartsResolvedLocation
from astro_api.geocoding import (
    GeocodingTimeout,
    PlaceNotFound,
    ResolvedLocation,
    resolve_place,
)
from astro_api.schemas import (
    NatalRequest,
    NatalResponse,
    SkyResponse,
    SynastryRequest,
    SynastryResponse,
    TransitsRequest,
    TransitsResponse,
)
from astro_api.settings import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]

API_DESCRIPTION = (
    "Stateless HTTP API exposing Western astrology calculations "
    "(natal charts, transits, synastry, current sky) computed via the Swiss "
    "Ephemeris. Consumed by an LLM client (Claude / ChatGPT) through Delegate, "
    "which auto-generates MCP tools from this OpenAPI spec."
)

app = FastAPI(title="astro-api", version="1.0.0", description=API_DESCRIPTION)

_API_KEY_SCHEME_NAME = "ApiKeyAuth"
_UNSECURED_PATHS = frozenset({"/healthz", "/openapi.json"})

_STATUS_TO_CODE: dict[int, str] = {
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
}


# ---------- Logging middleware ----------


@app.middleware("http")
async def logging_middleware(request: Request, call_next: Any) -> Any:
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    log_entry: dict[str, Any] = {
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "latency_ms": latency_ms,
    }
    error_code = getattr(request.state, "error_code", None)
    if error_code is not None:
        log_entry["error_code"] = error_code
    sys.stdout.write(json.dumps(log_entry) + "\n")
    sys.stdout.flush()
    return response


# ---------- Exception handlers (spec §7) ----------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _STATUS_TO_CODE.get(exc.status_code, "error")
    request.state.error_code = code
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": code, "detail": str(exc.detail)},
        headers=exc.headers,
    )


@app.exception_handler(PlaceNotFound)
async def place_not_found_handler(request: Request, exc: PlaceNotFound) -> JSONResponse:
    request.state.error_code = "place_not_found"
    return JSONResponse(
        status_code=422,
        content={"error": "place_not_found", "detail": f"birth_place not found: {exc}"},
    )


@app.exception_handler(GeocodingTimeout)
async def geocoding_timeout_handler(request: Request, _exc: GeocodingTimeout) -> JSONResponse:
    request.state.error_code = "geocoding_unavailable"
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "geocoding_unavailable",
            "detail": "Geocoding service timed out. Try again.",
        },
    )


@app.exception_handler(DateOutOfRange)
async def date_out_of_range_handler(request: Request, exc: DateOutOfRange) -> JSONResponse:
    request.state.error_code = "date_out_of_range"
    return JSONResponse(
        status_code=422,
        content={"error": "date_out_of_range", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    request.state.error_code = "internal_error"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "internal_error", "detail": "Internal server error."},
    )


# ---------- Helpers ----------


def _to_charts_location(location: ResolvedLocation) -> ChartsResolvedLocation:
    return ChartsResolvedLocation(
        latitude=location.latitude,
        longitude=location.longitude,
        timezone=location.timezone,
    )


def _surface_multiple_matches(warnings: list[str], location: ResolvedLocation) -> None:
    if "multiple_matches" in location.warnings and "multiple_matches" not in warnings:
        warnings.append("multiple_matches")


# ---------- Routes ----------


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/v1/natal",
    response_model=NatalResponse,
    dependencies=[Depends(require_api_key)],
)
def post_natal(
    payload: NatalRequest,
    settings: SettingsDep,
) -> NatalResponse:
    location = resolve_place(payload.subject.birth_place)
    house_system = payload.house_system or settings.default_house_system
    response = build_natal(payload.subject, _to_charts_location(location), house_system)
    _surface_multiple_matches(response.warnings, location)
    return response


@app.post(
    "/v1/transits",
    response_model=TransitsResponse,
    dependencies=[Depends(require_api_key)],
)
def post_transits(
    payload: TransitsRequest,
    settings: SettingsDep,
) -> TransitsResponse:
    location = resolve_place(payload.natal_subject.birth_place)
    house_system = payload.house_system or settings.default_house_system
    response = build_transits(
        payload.natal_subject,
        _to_charts_location(location),
        house_system,
        target_date=payload.target_date,
    )
    _surface_multiple_matches(response.warnings, location)
    return response


@app.post(
    "/v1/synastry",
    response_model=SynastryResponse,
    dependencies=[Depends(require_api_key)],
)
def post_synastry(
    payload: SynastryRequest,
    settings: SettingsDep,
) -> SynastryResponse:
    location_a = resolve_place(payload.subject_a.birth_place)
    location_b = resolve_place(payload.subject_b.birth_place)
    house_system = payload.house_system or settings.default_house_system
    response = build_synastry(
        payload.subject_a,
        _to_charts_location(location_a),
        payload.subject_b,
        _to_charts_location(location_b),
        house_system,
    )
    _surface_multiple_matches(response.subject_a.warnings, location_a)
    _surface_multiple_matches(response.subject_b.warnings, location_b)
    return response


@app.get(
    "/v1/sky",
    response_model=SkyResponse,
    dependencies=[Depends(require_api_key)],
)
def get_sky(date_time: datetime | None = None) -> SkyResponse:
    return build_sky(date_time)


# ---------- OpenAPI customization (apiKey security on X-API-Key) ----------


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes[_API_KEY_SCHEME_NAME] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
    }
    secured_requirement = [{_API_KEY_SCHEME_NAME: []}]
    for path, path_item in schema.get("paths", {}).items():
        if path in _UNSECURED_PATHS:
            continue
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                operation["security"] = secured_requirement
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]
