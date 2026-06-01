# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Utilities for reusing a local Codex CLI login without persisting secrets."""

from __future__ import annotations

import base64
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import aiohttp
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 test environments.
    tomllib = None

CODEX_AUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_MODEL_ID_PREFIX = "codex-login:"
CODEX_PROVIDER_TYPE = "codex_login"
CODEX_BASE_URL_DISPLAY = "codex://login"
CODEX_API_KEY_DISPLAY = ""
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_CODEX_REMOTE_CANDIDATE_MODELS = [
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
]
TOKEN_REFRESH_LEEWAY_SECONDS = 120


class CodexAuthError(RuntimeError):
    """Raised when the local Codex credentials cannot be used."""


class CodexRefreshRequired(RuntimeError):
    """Internal signal used when a request should refresh OAuth once."""


def _has_codex_credentials(root: Path) -> bool:
    return (root / "auth.json").is_file() or (root / "config.toml").is_file()


def _candidate_home_roots() -> list[Path]:
    override = os.getenv("CODEX_HOME_CANDIDATE_ROOTS")
    if override:
        return [
            Path(path).expanduser()
            for path in override.split(os.pathsep)
            if path.strip()
        ]
    return [Path("/home")]


def _discover_codex_home() -> Optional[Path]:
    for home_root in _candidate_home_roots():
        try:
            user_dirs = sorted(path for path in home_root.iterdir() if path.is_dir())
        except OSError:
            continue
        for user_dir in user_dirs:
            codex_dir = user_dir / ".codex"
            if _has_codex_credentials(codex_dir):
                return codex_dir
    return None


def codex_home() -> Path:
    configured_home = Path(os.getenv("CODEX_HOME") or Path.home() / ".codex").expanduser()
    if _has_codex_credentials(configured_home):
        return configured_home

    discovered_home = _discover_codex_home()
    return discovered_home or configured_home



def codex_model_id(model_name: str) -> str:
    return f"{CODEX_MODEL_ID_PREFIX}{str(model_name or '').strip()}"


def is_codex_model_id(model_id: Any) -> bool:
    return str(model_id or "").startswith(CODEX_MODEL_ID_PREFIX)


def model_name_from_codex_id(model_id: str) -> str:
    return str(model_id or "")[len(CODEX_MODEL_ID_PREFIX):].strip()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if tomllib is None:
        parsed: dict[str, Any] = {}
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip().strip("'\"")
        return parsed
    payload = tomllib.loads(content)
    return payload if isinstance(payload, dict) else {}


def _jwt_expires_at(token: str) -> Optional[int]:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    exp = data.get("exp") if isinstance(data, dict) else None
    return int(exp) if isinstance(exp, (int, float)) else None


def _is_oauth_logged_in(
    *,
    auth_mode: str,
    access_token: str,
    refresh_token: str,
    id_token: str,
) -> bool:
    if auth_mode == "chatgpt":
        return bool(access_token and refresh_token)
    return bool(not auth_mode and access_token and refresh_token and id_token)


def load_auth_state(home: Optional[Path] = None) -> dict[str, Any]:
    root = Path(home or codex_home()).expanduser()
    auth_path = root / "auth.json"
    payload = _read_json(auth_path)
    tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
    access_token = str(tokens.get("access_token") or "").strip()
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    id_token = str(tokens.get("id_token") or "").strip()
    account_id = str(tokens.get("account_id") or "").strip()
    auth_mode = str(payload.get("auth_mode") or "").strip()
    logged_in = _is_oauth_logged_in(
        auth_mode=auth_mode,
        access_token=access_token,
        refresh_token=refresh_token,
        id_token=id_token,
    )
    return {
        "auth_mode": auth_mode,
        "auth_scheme": "oauth" if logged_in else "none",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "account_id": account_id,
        "access_token_expires_at": _jwt_expires_at(access_token),
        "logged_in": logged_in,
        "codex_home": str(root),
        "auth_path": str(auth_path),
    }


def _normalize_model_id(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("slug") or value.get("id") or value.get("name")
        if value.get("supported_in_api") is False:
            return ""
    else:
        raw = value
    return str(raw or "").strip()


def load_available_models(home: Optional[Path] = None) -> list[str]:
    root = Path(home or codex_home()).expanduser()
    config = _read_toml(root / "config.toml")
    raw_models = _read_json(root / "models_cache.json").get("models")
    candidates: list[Any] = [config.get("model"), *(raw_models if isinstance(raw_models, list) else [])]
    candidates.extend(DEFAULT_CODEX_REMOTE_CANDIDATE_MODELS)

    models: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        model = _normalize_model_id(candidate)
        if not model or model in seen:
            continue
        models.append(model)
        seen.add(model)
    return models


def safe_status(home: Optional[Path] = None) -> dict[str, Any]:
    state = load_auth_state(home)
    models = load_available_models(home)
    return {
        "logged_in": bool(state.get("logged_in")),
        "auth_scheme": state.get("auth_scheme"),
        "has_access_token": bool(state.get("access_token")),
        "has_refresh_token": bool(state.get("refresh_token")),
        "has_account_id": bool(state.get("account_id")),
        "codex_home": state.get("codex_home"),
        "models": models,
        "default_model": models[0] if models else DEFAULT_CODEX_MODEL,
    }


def _parse_env_file(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    env: dict[str, str] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip().upper()] = value.strip().strip("'\"")
    return env


def proxy_for_url(request_url: str, home: Optional[Path] = None) -> Optional[str]:
    parsed = urlsplit(str(request_url or ""))
    if parsed.scheme == "https":
        keys = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY")
    elif parsed.scheme == "http":
        keys = ("HTTP_PROXY", "ALL_PROXY")
    else:
        return None
    env = {
        key: os.getenv(key) or os.getenv(key.lower()) or ""
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")
    }
    env.update(_parse_env_file(Path(home or codex_home()) / ".env"))
    for key in keys:
        value = str(env.get(key) or "").strip()
        parsed_proxy = urlsplit(value)
        if parsed_proxy.scheme in {"http", "https"} and parsed_proxy.netloc:
            return value
    return None


def build_headers(auth_state: dict[str, Any]) -> dict[str, str]:
    access_token = str(auth_state.get("access_token") or "").strip()
    if not access_token:
        raise CodexAuthError("本机 Codex access_token 不可用")
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    account_id = str(auth_state.get("account_id") or "").strip()
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    return headers


async def refresh_access_token(
    home: Optional[Path] = None,
    session: Optional[aiohttp.ClientSession] = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    root = Path(home or codex_home()).expanduser()
    auth_path = root / "auth.json"
    payload = _read_json(auth_path)
    tokens = payload.get("tokens") if isinstance(payload.get("tokens"), dict) else {}
    refresh_token = str(tokens.get("refresh_token") or "").strip()
    if not refresh_token:
        raise CodexAuthError("本机 Codex 缺少 refresh_token，无法刷新凭据")

    owns_session = session is None
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
    client = session or aiohttp.ClientSession(timeout=timeout)
    request_kwargs: dict[str, Any] = {
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "data": {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CODEX_AUTH_CLIENT_ID,
        },
    }
    proxy_url = proxy_for_url(CODEX_OAUTH_TOKEN_URL, root)
    if proxy_url:
        request_kwargs["proxy"] = proxy_url
    try:
        async with client.post(CODEX_OAUTH_TOKEN_URL, **request_kwargs) as resp:
            if resp.status >= 400:
                detail = await resp.text()
                raise CodexAuthError(f"刷新 Codex token 失败: HTTP {resp.status}: {detail[:300]}")
            data = await resp.json()
    finally:
        if owns_session:
            await client.close()

    refreshed_tokens = {
        "access_token": str(data.get("access_token") or tokens.get("access_token") or "").strip(),
        "refresh_token": str(data.get("refresh_token") or refresh_token).strip(),
        "id_token": str(data.get("id_token") or tokens.get("id_token") or "").strip(),
        "account_id": str(data.get("account_id") or tokens.get("account_id") or "").strip(),
    }
    payload["auth_mode"] = "chatgpt"
    payload["tokens"] = refreshed_tokens
    payload["last_refresh"] = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    _write_json(auth_path, payload)
    return load_auth_state(root)


async def refresh_tokens_if_needed(
    home: Optional[Path] = None,
    session: Optional[aiohttp.ClientSession] = None,
    leeway_seconds: int = TOKEN_REFRESH_LEEWAY_SECONDS,
) -> dict[str, Any]:
    state = load_auth_state(home)
    if not state.get("logged_in"):
        return state
    expires_at = state.get("access_token_expires_at")
    if expires_at is None:
        return state
    now_ts = int(dt.datetime.now(tz=dt.timezone.utc).timestamp())
    if int(expires_at) > now_ts + int(leeway_seconds):
        return state
    return await refresh_access_token(home=Path(str(state["codex_home"])), session=session)
