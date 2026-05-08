"""Загрузка списка заказов из СУЗ (OMS API v2 ЦРПТ)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import ssl
from typing import Any
from urllib.parse import urlencode

import httpx

from settings import Settings, get_settings

logger = logging.getLogger(__name__)


class SuzIntegrationError(RuntimeError):
    """
    Ошибка запроса к API СУЗ.

    ``suggest_transport_diagnostics``: True только при сбое транспорта (TLS/handshake и т.п.);
    при обычном HTTP-ответе с телом ошибки API подсказка про diagnostics неуместна.
    """

    def __init__(self, message: str, *, suggest_transport_diagnostics: bool = False) -> None:
        super().__init__(message)
        self.suggest_transport_diagnostics = suggest_transport_diagnostics


_UOT_CREDENTIAL_HINT = (
    " Обычно это несоответствие clientToken и omsId из URL: выпустите заголовок clientToken именно для "
    "этого OMS UUID в том же контуре sandbox, следите чтобы токен не истёк и база СУЗ (SUZ_API_BASE_URL) совпадает "
    "с контурами учётной записи."
)


def _as_bearer_header_value(token: str) -> str:
    """Нормализует токен для заголовка Authorization без дублирования Bearer."""
    raw = (token or "").strip()
    if raw.lower().startswith("bearer "):
        return raw
    return f"Bearer {raw}"


def _build_suz_auth_headers(
    token: str,
    *,
    product_group: str | None = None,
    with_json_content_type: bool = True,
) -> dict[str, str]:
    """
    Единые заголовки авторизации для СУЗ.

    Для v3 используем стандартную Bearer-авторизацию без clientToken.
    """
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Authorization": _as_bearer_header_value(token),
    }
    if product_group:
        headers["X-Product-Group"] = product_group
    if with_json_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _iter_suz_flat_errors(parsed: dict[str, Any]) -> list[str]:
    """Тексты из globalErrors/errors и смежных типовых полей ответа СУЗ."""
    acc: list[str] = []

    glob = parsed.get("globalErrors")
    if isinstance(glob, list):
        for item in glob:
            if isinstance(item, dict):
                txt = (
                    item.get("error")
                    or item.get("message")
                    or item.get("errorMessage")
                    or item.get("errorDescription")
                    or ""
                ).strip()
                code = item.get("errorCode")
                if txt:
                    acc.append(f"{txt} (код {code})" if code is not None else txt)
                elif code is not None:
                    acc.append(f"ошибка {code}")
            elif isinstance(item, str) and item.strip():
                acc.append(item.strip())

    errs = parsed.get("errors") or parsed.get("validationErrors") or parsed.get("fieldErrors")
    if isinstance(errs, list):
        for item in errs:
            if isinstance(item, dict):
                txt = (
                    item.get("message")
                    or item.get("error")
                    or item.get("detail")
                    or item.get("errorMessage")
                    or ""
                ).strip()
                if txt:
                    acc.append(txt)
            elif isinstance(item, str) and item.strip():
                acc.append(item.strip())

    raw_msg = parsed.get("message") or parsed.get("errorDescription") or parsed.get("description")
    if isinstance(raw_msg, str) and raw_msg.strip():
        acc.append(raw_msg.strip())

    return acc


def _expects_uot_credential_notice(parsed: dict[str, Any]) -> bool:
    """Признак ошибки 1090 / проверки учётных данных УОТ (не транспорт, не TLS)."""
    ec = parsed.get("errorCode")
    if ec == 1090 or ec == "1090":
        return True
    glo = parsed.get("globalErrors")
    if isinstance(glo, list):
        for item in glo:
            if isinstance(item, dict):
                iec = item.get("errorCode")
                if iec == 1090 or str(iec) == "1090":
                    return True
    msgs = _iter_suz_flat_errors(parsed)
    for m in msgs:
        low = m.lower()
        if "1090" in m:
            return True
        if ("учётных данных" in low or "учетных данных" in low) and "уот" in low:
            return True
    return False


def _format_suz_http_error_detail(*, http_code: int, url: str | None, body_text: str) -> str:
    """Единое человекочитаемое сообщение для HTTP≠2xx без подсказок про diagnostics."""
    tail = body_text.strip()[:2000]
    parsed: Any = None
    try:
        parsed = json.loads(body_text)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    if isinstance(parsed, dict):
        lines = _iter_suz_flat_errors(parsed)
        if lines:
            head = "; ".join(lines)
            msg = f"СУЗ отклонила запрос ({http_code}). {head}"
            if _expects_uot_credential_notice(parsed):
                msg += _UOT_CREDENTIAL_HINT
            if url:
                msg += f" Запрос: {url}"
            return msg

    snippet = tail or "(пустое тело ответа)"
    base = (
        f"СУЗ отклонила запрос ({http_code}): {snippet}"
        if url is None
        else f"СУЗ вернула HTTP {http_code} для {url}: {snippet}"
    )
    low = snippet.lower()
    if "учётных данных" in low or "учетных данных" in low:
        base += _UOT_CREDENTIAL_HINT
    return base


def _apply_legacy_tls_hacks(ctx: ssl.SSLContext) -> None:
    """Помогает на редких хостах с нестандартным TLS-хендшейком (OpenSSL в Docker)."""
    if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
        try:
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        except ssl.SSLError:
            pass


def suz_sandbox_ssl_context() -> ssl.SSLContext:
    """
    TLS без проверки сертификата и hostname для песочницы СУЗ (нет ГОСТ в стандартном Python).

    Передаётся в httpx как ``verify=context`` наряду с ``verify=False`` — оба режима отключают проверку,
    контекст дополнительно включает OP_LEGACY_SERVER_CONNECT там, где это доступно в OpenSSL.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _apply_legacy_tls_hacks(ctx)
    return ctx


def _ctx_verified(cipher: str | None, tls12_only: bool) -> ssl.SSLContext | None:
    try:
        ctx = ssl.create_default_context()
        if tls12_only:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        if cipher:
            ctx.set_ciphers(cipher)
        return ctx
    except ssl.SSLError:
        return None


def _ctx_unverified(cipher: str | None, tls12_only: bool) -> ssl.SSLContext | None:
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _apply_legacy_tls_hacks(ctx)
        if tls12_only:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        if cipher:
            ctx.set_ciphers(cipher)
        return ctx
    except ssl.SSLError:
        return None


def _ctx_insecure_versioned(
    tls_min: ssl.TLSVersion | None,
    tls_max: ssl.TLSVersion | None,
    cipher: str | None,
) -> ssl.SSLContext | None:
    """Нестандартное сужение версий TLS (UNSUPPORTED_PROTOCOL / капризы стенда)."""
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        _apply_legacy_tls_hacks(ctx)
        if tls_min is not None:
            ctx.minimum_version = tls_min
        if tls_max is not None:
            ctx.maximum_version = tls_max
        if cipher:
            ctx.set_ciphers(cipher)
        return ctx
    except ssl.SSLError:
        return None


def _suz_verify_candidates(settings: Settings) -> list[bool | ssl.SSLContext]:
    """
    Варианты verify для httpx.

    Важно: SUZ_TLS_VERIFY=false отключает проверку сертификата, но не меняет набор шифров;
    поэтому при verify=false всё равно перебираем явные SSLContext с разными cipher / TLS 1.2 only.
    """
    ciphers: list[str | None] = [
        None,
        "DEFAULT:@SECLEVEL=0",
        "DEFAULT:@SECLEVEL=1",
        "ALL:@SECLEVEL=0",
    ]
    tls12_modes = (False, True)
    acc: list[bool | ssl.SSLContext] = []

    if settings.suz_tls_verify:
        acc.append(True)
        if settings.suz_ssl_compat:
            for tls12 in tls12_modes:
                for ci in ciphers:
                    if ci is None and not tls12:
                        continue
                    ctx = _ctx_verified(ci, tls12)
                    if ctx is not None:
                        acc.append(ctx)
    else:
        acc.append(False)
        for tls12 in tls12_modes:
            for ci in ciphers:
                ctx = _ctx_unverified(ci, tls12)
                if ctx is not None:
                    acc.append(ctx)

    return acc if acc else [True]


def _suz_httpx_verify_options(settings: Settings) -> list[bool | ssl.SSLContext]:
    """
    Вариант verify для httpx к хостам СУЗ.

    Если SUZ_TLS_VERIFY=false — сначала кастомный SSLContext без проверки (sandbox / нестандартные цепочки),
    затем явный ``verify=False`` у AsyncClient и дальше перебор cipher/TLS версий.
    Если true — только строгая проверка и ослабленные verified-контексты (SUZ_SSL_COMPAT).
    """
    if not settings.suz_tls_verify:
        opts: list[bool | ssl.SSLContext] = [suz_sandbox_ssl_context(), False]
        for tls12 in (False, True):
            for ci in ("DEFAULT:@SECLEVEL=0", "ALL:@SECLEVEL=0", None):
                ctx = _ctx_unverified(ci, tls12)
                if ctx is not None:
                    opts.append(ctx)
        rngs: tuple[tuple[ssl.TLSVersion | None, ssl.TLSVersion | None], ...] = (
            (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3),
            (ssl.TLSVersion.TLSv1_3, ssl.TLSVersion.TLSv1_3),
            (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_2),
        )
        for mn, mx in rngs:
            for ci in ("DEFAULT:@SECLEVEL=0", None):
                x = _ctx_insecure_versioned(mn, mx, ci)
                if x is not None:
                    opts.append(x)
        return opts
    return _suz_verify_candidates(settings)


def _curl_tls_flag_variants() -> tuple[tuple[str, ...], ...]:
    """
    Варианты флагов TLS для curl после неудачи httpx.

    Раньше использовали только TLS 1.2 max — при этом TLS 1.3-only серверы дают:
    curl: (35) ... unsupported protocol. Сначала даём curl согласовать версию сам.
    """
    return (
        (),
        ("--tlsv1.3",),
        ("--tlsv1.2", "--tls-max", "1.2"),
    )


async def _curl_get_json(
    full_url: str,
    token: str,
    timeout_sec: int,
    tls_extra: tuple[str, ...] = (),
) -> tuple[int, dict[str, Any] | list[Any] | None, str]:
    """Обход через curl (другой стек TLS). Возвращает (http_code, json_or_none, raw_prefix)."""
    if not shutil.which("curl"):
        raise OSError("curl not found")

    args = [
        "curl",
        "-sS",
        "--http1.1",
        *tls_extra,
        "-k",
        "-H",
        f"clientToken: {token}",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Accept: application/json",
        "-H",
        "Content-Type: application/json",
        "-w",
        "\\n%{http_code}",
        "--max-time",
        str(timeout_sec),
        full_url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    raw_out, raw_err = await proc.communicate()
    err_t = raw_err.decode(errors="replace").strip()
    out_t = raw_out.decode(errors="replace")
    if proc.returncode != 0:
        raise OSError(err_t or out_t[:500] or f"curl exit {proc.returncode}")

    if "\n" not in out_t:
        raise OSError(out_t[:800])
    body, _sep, code_s = out_t.rpartition("\n")
    try:
        code = int(code_s.strip())
    except ValueError as exc:
        raise OSError(out_t[:800]) from exc

    try:
        parsed: dict[str, Any] | list[Any] | None = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return code, parsed, body[:2000]


async def _curl_post_json(
    full_url: str,
    token: str,
    product_group: str,
    json_body: dict[str, Any],
    timeout_sec: int,
    tls_extra: tuple[str, ...] = (),
) -> tuple[int, dict[str, Any] | list[Any] | None, str]:
    """POST JSON в СУЗ через curl — иной стек TLS, чем у httpx/Python ssl."""
    if not shutil.which("curl"):
        raise OSError("curl not found")

    payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    args = [
        "curl",
        "-sS",
        "--http1.1",
        *tls_extra,
        "-k",
        "-X",
        "POST",
        "-H",
        f"Authorization: {_as_bearer_header_value(token)}",
        "-H",
        "Accept: application/json",
        "-H",
        "Content-Type: application/json; charset=utf-8",
        "-H",
        f"X-Product-Group: {product_group}",
        "--data-binary",
        "@-",
        "-w",
        "\\n%{http_code}",
        "--max-time",
        str(timeout_sec),
        full_url,
    ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    raw_out, raw_err = await proc.communicate(input=payload)
    err_t = raw_err.decode(errors="replace").strip()
    out_t = raw_out.decode(errors="replace")
    if proc.returncode != 0:
        raise OSError(err_t or out_t[:500] or f"curl exit {proc.returncode}")

    if "\n" not in out_t:
        raise OSError(out_t[:800])
    body, _sep, code_s = out_t.rpartition("\n")
    try:
        code = int(code_s.strip())
    except ValueError as exc:
        raise OSError(out_t[:800]) from exc

    try:
        parsed_post: dict[str, Any] | list[Any] | None = json.loads(body) if body.strip() else None
    except json.JSONDecodeError:
        parsed_post = None
    return code, parsed_post, body[:2000]


def _first_str(d: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _first_int(d: dict[str, Any], *keys: str) -> int | None:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        s = str(v).strip()
        if s.isdigit():
            return int(s)
    return None


def _normalize_gtin(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(c for c in str(raw) if c.isdigit())
    if not digits:
        return None
    if len(digits) > 14:
        digits = digits[-14:]
    return digits.zfill(14) if len(digits) <= 14 else digits[:14]


def _as_order_dicts(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("orders", "result", "data", "items", "content"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        if payload.keys() >= {"orderId", "gtin"} or payload.keys() >= {"order_id", "gtin"}:
            return [payload]
    return []


def _parse_remote_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    order_id = _first_str(raw, "orderId", "order_id", "id", "orderID", "emissionOrderId")
    if not order_id:
        return None
    gtin = _normalize_gtin(_first_str(raw, "gtin", "GTIN", "productCode", "product_code", "barcode"))
    qty = _first_int(raw, "quantity", "qty", "orderQuantity", "order_quantity", "requestedQuantity")
    status_raw = _first_str(raw, "orderStatus", "order_status", "status", "state", "orderState")
    return {
        "order_id": order_id,
        "gtin": gtin,
        "quantity": max(1, qty or 1),
        "status_raw": status_raw or "",
    }


def _map_suz_status(status_raw: str) -> str:
    u = status_raw.strip().upper().replace(" ", "_")
    if u in {"CREATED", "NEW", "DRAFT", "REGISTERED"}:
        return "created"
    if u in {
        "PENDING",
        "IN_PROGRESS",
        "PROCESSING",
        "SENT",
        "SUBMITTED",
        "AWAITING",
        "WAITING",
        "ACTIVE",
    }:
        return "pending"
    if u in {"AVAILABLE", "READY", "COMPLETED", "DONE", "CLOSED", "SUCCESS", "EXPORTED"}:
        return "available"
    if u in {"REJECTED", "DECLINED", "ERROR", "FAILED", "CANCELLED", "CANCELED"}:
        return "rejected"
    return "pending"


def map_suz_status_to_emission(status_raw: str) -> str:
    """Значение для EmissionOrderStatus (created|pending|available|rejected)."""
    return _map_suz_status(status_raw)


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _as_order_dicts(payload):
        parsed = _parse_remote_row(raw)
        if parsed:
            rows.append(parsed)
    return rows


async def _suz_dispatch_httpx(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict[str, str] | None,
    json_body: dict[str, Any] | None,
) -> tuple[httpx.Response | None, BaseException | None]:
    settings = get_settings()
    opts = _suz_httpx_verify_options(settings)
    last_err: BaseException | None = None
    m = method.upper()
    for idx, verify in enumerate(opts):
        try:
            async with httpx.AsyncClient(
                timeout=settings.suz_timeout_seconds,
                verify=verify,
                trust_env=False,
            ) as client:
                if m == "GET":
                    response = await client.get(url, headers=headers, params=params)
                else:
                    response = await client.post(url, headers=headers, params=params, json=json_body)
            logger.debug(
                "SUZ httpx %s ok attempt %s verify_type=%s",
                method,
                idx + 1,
                type(verify).__name__,
            )
            return response, None
        except httpx.RequestError as exc:
            last_err = exc
            logger.debug("SUZ httpx %s fail attempt %s: %s", method, idx + 1, exc)
            continue
    return None, last_err


_PRODUCT_GROUPS_WITH_CISTYPE = frozenset({"perfum", "lp"})
_LIGHT_GROUPS = frozenset({"light"})


def build_suz_create_order_body(
    settings: Settings,
    *,
    product_group: str,
    gtin14: str,
    quantity: int,
    production_order_id: str,
) -> dict[str, Any]:
    """
    JSON-тело POST /api/v3/orders?omsId=... по OMS API v3.

    Контуры отличаются допустимыми enum — выставите SUZ_ORDER_* в .env по инструкции к вашему контуру СУЗ.
    """
    g = (product_group or "perfum").strip().strip("/").lower() or "perfum"
    line: dict[str, Any] = {
        "gtin": gtin14,
        "quantity": int(quantity),
        "serialNumberType": settings.suz_serial_number_type,
        "templateId": int(settings.suz_marking_template_id),
    }
    if g in _PRODUCT_GROUPS_WITH_CISTYPE:
        line["cisType"] = settings.suz_product_cis_type
    envelope: dict[str, Any] = {
        "contactPerson": settings.suz_order_contact_person,
        "releaseMethodType": settings.suz_order_release_method_type,
        "createMethodType": settings.suz_order_create_method_type,
        "productionOrderId": production_order_id,
        "products": [line],
    }
    if g in _LIGHT_GROUPS:
        envelope["contractNumber"] = settings.suz_order_contract_number
        envelope["contractDate"] = settings.suz_order_contract_date
    return envelope


async def fetch_suz_orders_raw(*, oms_id: str | None = None) -> tuple[list[dict[str, Any]], str]:
    """
    GET /api/v3/orders?omsId=...

    Возвращает нормализованные строки заказов и URL запроса (для сообщений об ошибках).
    """
    settings = get_settings()
    base = (settings.suz_api_base_url or "").strip().rstrip("/")
    token = (settings.suz_client_token or "").strip()
    oms_resolved = (oms_id or settings.suz_oms_id or "").strip()

    if not base:
        raise SuzIntegrationError(
            "Не задан SUZ_API_BASE_URL (базовый URL СУЗ / шлюза OMS из инструкции к вашему контуру)."
        )
    if not token:
        raise SuzIntegrationError(
            "Не задан SUZ_CLIENT_TOKEN (заголовок clientToken после авторизации в API СУЗ)."
        )
    if not oms_resolved:
        raise SuzIntegrationError(
            "Не задан omsId: укажите SUZ_OMS_ID или добавьте устройство с OMS ID в настройках."
        )

    path = f"{base}/api/v3/orders"
    params = {"omsId": oms_resolved}
    full_url = f"{path}?{urlencode(params)}"

    headers = _build_suz_auth_headers(token, product_group=settings.suz_product_group)

    verify_opts = _suz_httpx_verify_options(settings)
    response, last_err = await _suz_dispatch_httpx(
        method="GET",
        url=path,
        headers=headers,
        params=params,
        json_body=None,
    )

    if response is None and settings.suz_curl_fallback:
        tmax = max(1, int(settings.suz_timeout_seconds))
        for curl_tls in _curl_tls_flag_variants():
            try:
                code, payload, raw_pref = await _curl_get_json(full_url, token, tmax, tls_extra=curl_tls)
                if code != 200:
                    curl_body = ""
                    if isinstance(payload, dict) or isinstance(payload, list):
                        curl_body = json.dumps(payload, ensure_ascii=False)
                    else:
                        curl_body = raw_pref
                    raise SuzIntegrationError(
                        _format_suz_http_error_detail(http_code=code, url=full_url, body_text=curl_body)
                    )
                if payload is None:
                    raise SuzIntegrationError(f"СУЗ (curl) не-JSON: {raw_pref[:800]}")
                rows = _rows_from_payload(payload)
                return rows, full_url
            except OSError as exc:
                last_err = exc
                label = "default TLS" if not curl_tls else " ".join(curl_tls)
                logger.warning("SUZ curl fallback (%s) failed: %s", label, exc)

    if response is None:
        msg = (
            f"Не удалось установить TLS с СУЗ после {len(verify_opts)} вариантов httpx"
            + (" и curl." if settings.suz_curl_fallback else ".")
            + f" Последняя ошибка: {last_err}. "
            "Убедитесь, что SUZ_SSL_COMPAT=true в .env. "
            "Если контур требует ГОСТ-TLS (КриптоПро), запросы из стандартного контейнера могут быть невозможны — используйте шлюз на стороне организации или машину с сертифицированным СКЗИ."
        )
        raise SuzIntegrationError(msg, suggest_transport_diagnostics=True) from last_err

    if response.status_code != 200:
        raise SuzIntegrationError(
            _format_suz_http_error_detail(
                http_code=response.status_code,
                url=str(response.request.url),
                body_text=response.text,
            )
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise SuzIntegrationError(f"СУЗ вернула не-JSON: {response.text[:500]}") from exc

    return _rows_from_payload(payload), str(response.request.url)


async def submit_suz_emission_order(
    *,
    oms_id: str | None,
    json_body: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """
    POST /api/v3/orders?omsId=...

    Возвращает удалённый orderId и сырое тело ответа (dict).
    """
    settings = get_settings()
    base = (settings.suz_api_base_url or "").strip().rstrip("/")
    token = (settings.suz_auth_token or settings.suz_client_token or "").strip()
    oms_resolved = (oms_id or settings.suz_oms_id or "").strip()

    if not base:
        raise SuzIntegrationError(
            "Не задан SUZ_API_BASE_URL (базовый URL СУЗ / шлюза OMS из инструкции к вашему контуру)."
        )
    if not token:
        raise SuzIntegrationError(
            "Не задан токен авторизации СУЗ: укажите SUZ_AUTH_TOKEN (Bearer для API v3) "
            "или SUZ_CLIENT_TOKEN как fallback."
        )
    if not oms_resolved:
        raise SuzIntegrationError(
            "Не задан omsId: укажите SUZ_OMS_ID или добавьте устройство с OMS ID в настройках."
        )

    path = f"{base}/api/v3/orders"
    params = {"omsId": oms_resolved}

    headers = _build_suz_auth_headers(token, product_group=settings.suz_product_group)

    verify_opts = _suz_httpx_verify_options(settings)
    response, last_err = await _suz_dispatch_httpx(
        method="POST",
        url=path,
        headers=headers,
        params=params,
        json_body=json_body,
    )

    full_url_post = f"{path}?{urlencode(params)}"
    if response is None and settings.suz_curl_fallback:
        tmax = max(1, int(settings.suz_timeout_seconds))
        for curl_tls in _curl_tls_flag_variants():
            try:
                code, parsed, raw_pref = await _curl_post_json(
                    full_url_post,
                    token,
                    settings.suz_product_group,
                    json_body,
                    tmax,
                    tls_extra=curl_tls,
                )
                if code not in (200, 201):
                    curl_body = ""
                    if isinstance(parsed, dict) or isinstance(parsed, list):
                        curl_body = json.dumps(parsed, ensure_ascii=False)
                    else:
                        curl_body = raw_pref
                    raise SuzIntegrationError(
                        _format_suz_http_error_detail(http_code=code, url=full_url_post, body_text=curl_body)
                    )
                if not isinstance(parsed, dict):
                    raise SuzIntegrationError(f"СУЗ (curl POST) не-JSON объект: {raw_pref[:800]}")
                remote_oid_c = _first_str(parsed, "orderId", "order_id", "orderID")
                if not remote_oid_c:
                    raise SuzIntegrationError(f"Ответ СУЗ (curl) без orderId: {raw_pref[:2000]}")
                return remote_oid_c, parsed
            except OSError as exc:
                last_err = exc
                lbl = "default TLS" if not curl_tls else " ".join(curl_tls)
                logger.warning("SUZ curl POST (%s) failed: %s", lbl, exc)

    if response is None:
        msg = (
            f"Не удалось установить TLS при POST в СУЗ после {len(verify_opts)} вариантов httpx"
            + (" и curl POST." if settings.suz_curl_fallback else ".")
            + f" Последняя ошибка: {last_err}. "
            "Проверьте SUZ_API_BASE_URL (часть стендов — отдельный хост TLS), SUZ_TLS_VERIFY=false и "
            "SUZ_CURL_FALLBACK=true. Если ошибка сохраняется, контур может требовать ГОСТ-TLS без обхода."
        )
        raise SuzIntegrationError(msg, suggest_transport_diagnostics=True) from last_err

    if response.status_code not in (200, 201):
        raise SuzIntegrationError(
            _format_suz_http_error_detail(
                http_code=response.status_code,
                url=str(response.request.url),
                body_text=response.text,
            )
        )

    try:
        payload_any = response.json()
    except ValueError as exc:
        raise SuzIntegrationError(f"СУЗ вернула не-JSON: {response.text[:500]}") from exc

    if not isinstance(payload_any, dict):
        raise SuzIntegrationError(f"СУЗ вернула не объект JSON: {str(payload_any)[:500]}")

    remote_oid = _first_str(payload_any, "orderId", "order_id", "orderID")
    if not remote_oid:
        raise SuzIntegrationError(f"Ответ СУЗ не содержит orderId: {response.text[:2000]}")

    return remote_oid, payload_any
