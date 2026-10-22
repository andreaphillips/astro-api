import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from astro_api.settings import Settings, get_settings

API_KEY_HEADER = "X-API-Key"

ApiKeyHeader = Annotated[str | None, Header(alias=API_KEY_HEADER)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def require_api_key(settings: SettingsDep, x_api_key: ApiKeyHeader = None) -> None:
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
        )
    # Compare as bytes: compare_digest rejects non-ASCII str, and header values
    # arrive latin-1 decoded, so a non-ASCII key would raise instead of 401.
    if not secrets.compare_digest(
        x_api_key.encode("utf-8"), settings.astro_api_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-API-Key.",
        )
