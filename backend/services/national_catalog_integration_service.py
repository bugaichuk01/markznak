"""Интеграция отправки карточек в Национальный каталог ЧЗ."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from models import ProductCard
from settings import get_settings


class NationalCatalogIntegrationError(RuntimeError):
    """Ошибка отправки карточки во внешний контур Национального каталога."""


@dataclass
class NationalCatalogSubmissionResult:
    remote_status: str
    feed_id: str | None
    feed_status: str | None
    feed_payload: dict[str, Any] | None


def _serialize_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        return payload if isinstance(payload, dict) else {"payload": payload}
    except ValueError:
        return {"raw_text": response.text, "headers": dict(response.headers)}


def _extract_base_url(send_url: str) -> str:
    marker = "/v3/"
    idx = send_url.find(marker)
    return send_url[:idx] if idx > 0 else send_url.rstrip("/")


def _active_cat_ids_from_categories(categories: list[dict[str, Any]]) -> list[int]:
    """Идентификаторы активных категорий НК из ответа /v3/categories (порядок сохраняем)."""
    seen: set[int] = set()
    out: list[int] = []
    for c in categories:
        if not isinstance(c, dict) or c.get("category_active") is not True:
            continue
        raw = c.get("cat_id")
        cid: int | None
        if isinstance(raw, int):
            cid = raw
        elif isinstance(raw, str) and raw.isdigit():
            cid = int(raw)
        else:
            cid = None
        if cid is not None and cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


async def _fetch_required_attrs(
    client: httpx.AsyncClient,
    send_url: str,
    auth_params: dict[str, str],
    headers: dict[str, str],
    tnved: str,
    cat_id: int | None,
    active_cat_ids: list[int],
) -> tuple[list[dict[str, Any]], int | None]:
    """
    Возвращает обязательные атрибуты и cat_id, с которым сработал запрос (если был).

    В sandbox НК запрос /v3/attributes по tnved часто отвечает 404; по cat_id из /v3/categories — 200.
    """
    base_url = f"{_extract_base_url(send_url)}/v3/attributes"
    attempts: list[dict[str, Any]] = []
    if cat_id:
        attempts.append({"attr_type": "m", "cat_id": cat_id})
    else:
        for cid in active_cat_ids:
            attempts.append({"attr_type": "m", "cat_id": cid})
    attempts.append({"attr_type": "m", "tnved": tnved})

    errors: list[str] = []
    for query in attempts:
        response = await client.get(base_url, params={**auth_params, **query}, headers=headers)
        if response.status_code != 200:
            errors.append(
                "Не удалось получить обязательные атрибуты НК "
                f"[status={response.status_code}, url={response.request.url}]: {_serialize_response(response)}"
            )
            continue

        payload = _serialize_response(response)
        result = payload.get("result")
        if isinstance(result, list):
            resolved: int | None = None
            cid_raw = query.get("cat_id")
            if isinstance(cid_raw, int):
                resolved = cid_raw
            elif isinstance(cid_raw, str) and cid_raw.isdigit():
                resolved = int(cid_raw)
            return result, resolved
        errors.append(
            "НК вернул неожиданный формат ответа по атрибутам "
            f"[url={response.request.url}]: {payload}"
        )

    details = " | ".join(errors) if errors else "Не удалось получить обязательные атрибуты НК"
    raise NationalCatalogIntegrationError(details)


async def _fetch_categories_by_tnved(
    client: httpx.AsyncClient,
    send_url: str,
    auth_params: dict[str, str],
    headers: dict[str, str],
    tnved: str,
) -> list[dict[str, Any]]:
    tnved_candidates = [tnved]
    if len(tnved) >= 4 and tnved[:4] != tnved:
        tnved_candidates.append(tnved[:4])

    last_error: str | None = None
    for candidate in tnved_candidates:
        response = await client.get(
            f"{_extract_base_url(send_url)}/v3/categories",
            params={**auth_params, "tnved": candidate},
            headers=headers,
        )
        if response.status_code != 200:
            last_error = (
                "Не удалось получить категории НК по ТН ВЭД "
                f"[status={response.status_code}, url={response.request.url}]: {_serialize_response(response)}"
            )
            continue
        payload = _serialize_response(response)
        result = payload.get("result")
        if isinstance(result, list):
            return result
        last_error = f"НК вернул неожиданный формат categories для tnved={candidate}: {payload}"

    raise NationalCatalogIntegrationError(last_error or "Не удалось получить категории НК по ТН ВЭД")


def _validate_category_access(categories: list[dict[str, Any]], tnved: str, cat_id: int | None) -> None:
    if not categories:
        raise NationalCatalogIntegrationError(
            f"По ТН ВЭД {tnved} не найдено категорий НК для текущего участника."
        )

    active_categories = [
        c for c in categories if isinstance(c, dict) and (c.get("category_active") is True)
    ]
    if not active_categories:
        raise NationalCatalogIntegrationError(
            "Для данного ТН ВЭД в НК нет активных категорий для текущего участника. "
            "Проверьте подключенные товарные группы в Едином ЛК ГИС МТ."
        )

    if cat_id is None:
        return
    if not any(isinstance(c, dict) and c.get("cat_id") == cat_id for c in active_categories):
        available = [c.get("cat_id") for c in active_categories if isinstance(c, dict)]
        raise NationalCatalogIntegrationError(
            f"Категория {cat_id} недоступна для ТН ВЭД {tnved} у текущего участника. "
            f"Доступные категории: {available}"
        )


def _resolve_remote_status(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict) and result.get("feed_id"):
        return "sent"
    raw_status = str(payload.get("status") or "").strip().lower()
    if raw_status in {"published", "sent"}:
        return raw_status
    return "sent"


def _extract_feed_id(payload: dict[str, Any]) -> str | None:
    result = payload.get("result")
    if isinstance(result, dict):
        feed_id = result.get("feed_id")
        if feed_id is not None:
            return str(feed_id)
    return None


def _pick_attr_value_type(attr: dict[str, Any], fallback: str = "") -> str:
    value_types = attr.get("attr_value_type")
    if isinstance(value_types, list):
        for item in value_types:
            if isinstance(item, str) and item.strip() and item.strip() != "---":
                return item.strip()
    return fallback


def _build_required_attrs(card: ProductCard, required_attrs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
    attrs: list[dict[str, Any]] = []
    unresolved: list[int] = []

    for attr in required_attrs:
        if not isinstance(attr, dict):
            continue
        raw_id = attr.get("attr_id")
        if not str(raw_id).isdigit():
            continue
        attr_id = int(raw_id)
        presets = attr.get("attr_preset") if isinstance(attr.get("attr_preset"), list) else []

        if attr_id == 2478:  # Полное наименование товара
            attrs.append({"attr_id": attr_id, "attr_value": card.name})
        elif attr_id == 2504:  # Товарный знак
            attrs.append({"attr_id": attr_id, "attr_value": "NO_BRAND"})
        elif attr_id == 3959:  # Группа ТНВЭД
            attrs.append({"attr_id": attr_id, "attr_value": card.tn_ved[:4]})
        elif attr_id == 13933:  # Код ТНВЭД (10 знаков, лучше из пресета)
            preset_tnved = next((p for p in presets if isinstance(p, str) and p.isdigit() and len(p) == 10), "")
            value = preset_tnved or (card.tn_ved if len(card.tn_ved) == 10 else "")
            if value:
                attrs.append({"attr_id": attr_id, "attr_value": value})
            else:
                unresolved.append(attr_id)
        elif attr_id == 2716:  # Заявленный объем
            attrs.append(
                {
                    "attr_id": attr_id,
                    "attr_value": "50",
                    "attr_value_type": _pick_attr_value_type(attr, "мл"),
                }
            )
        elif attr_id == 1034:  # Тип парфюмерии
            value = "ДУХИ" if "ДУХИ" in presets else (presets[0] if presets else "")
            if value:
                attrs.append({"attr_id": attr_id, "attr_value": value})
            else:
                unresolved.append(attr_id)
        elif attr_id == 2710:  # Тип упаковки
            preferred = "ФЛАКОН"
            value = preferred if preferred in presets else (presets[0] if presets else "")
            if value:
                attrs.append({"attr_id": attr_id, "attr_value": value})
            else:
                unresolved.append(attr_id)
        elif attr_id == 2713:  # Материал упаковки
            preferred = "СТЕКЛО"
            value = preferred if preferred in presets else (presets[0] if presets else "")
            if value:
                attrs.append({"attr_id": attr_id, "attr_value": value})
            else:
                unresolved.append(attr_id)
        elif attr_id == 13836:  # Номер технического регламента
            value = presets[0] if presets else ""
            if value:
                attrs.append({"attr_id": attr_id, "attr_value": value})
            else:
                unresolved.append(attr_id)
        elif attr_id == 2630:  # Страна производства
            attrs.append({"attr_id": attr_id, "attr_value": "RU"})
        else:
            unresolved.append(attr_id)

    return attrs, sorted(set(unresolved))


def _build_entry_variants(
    card: ProductCard,
    cat_id: int | None,
    required_attrs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    required_built_attrs, _ = _build_required_attrs(card, required_attrs)

    base_payload: dict[str, Any] = {
        "good_name": card.name,
        "tnved": card.tn_ved,
        "brand": "NO_BRAND",
        "good_attrs": required_built_attrs,
    }

    variants: list[dict[str, Any]] = []
    if card.gtin:
        gtin_payload = {
            **base_payload,
            "gtin": card.gtin,
            "identified_by": [
                {
                    "value": card.gtin,
                    "type": "gtin",
                    "multiplier": 1,
                    "level": "trade-unit",
                    "unit": "шт",
                }
            ],
        }
        if cat_id:
            variants.append({**gtin_payload, "categories": [cat_id]})
            variants.append({**gtin_payload, "categories": [{"cat_id": cat_id}]})
        variants.append(gtin_payload)
        return variants

    # Для техкарточек в НК часто ожидают числовой флаг.
    tech_payload = {**base_payload, "is_tech_gtin": 1}
    if cat_id:
        variants.append({**tech_payload, "categories": [cat_id]})
        variants.append({**tech_payload, "categories": [{"cat_id": cat_id}]})
    variants.append(tech_payload)
    return variants


def _build_request_bodies(entry: dict[str, Any]) -> list[Any]:
    # НК в разных сценариях принимает feed в разных формах.
    return [
        entry,
        [entry],
        {"entries": [entry]},
    ]


async def fetch_feed_status(
    *,
    feed_id: str,
    settings_send_url: str,
    auth_params: dict[str, str],
    headers: dict[str, str],
    supplier_key: str | None,
    timeout_seconds: float,
) -> tuple[str | None, dict[str, Any] | None]:
    params: dict[str, Any] = {**auth_params, "feed_id": feed_id, "verbose": "true"}
    if supplier_key:
        params["supplier_key"] = supplier_key

    status_url = f"{_extract_base_url(settings_send_url)}/v3/feed-status"
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.get(status_url, params=params, headers=headers)
    if response.status_code != 200:
        return None, _serialize_response(response)

    payload = _serialize_response(response)
    result = payload.get("result")
    if isinstance(result, dict):
        raw_status = result.get("status")
        return str(raw_status) if raw_status is not None else None, payload
    return None, payload


async def send_product_card(card: ProductCard, cat_id: int | None = None) -> NationalCatalogSubmissionResult:
    """Отправляет карточку товара в Национальный каталог, возвращает итоговый статус."""
    settings = get_settings()

    if not settings.national_catalog_send_url:
        raise NationalCatalogIntegrationError(
            "Не настроен URL интеграции Национального каталога (NATIONAL_CATALOG_SEND_URL)"
        )

    params: dict[str, str] = {}
    if settings.national_catalog_api_key:
        params["apikey"] = settings.national_catalog_api_key

    headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    # Если есть API key, используем только его. Bearer-токен применяем как fallback.
    if not params and settings.national_catalog_auth_token:
        headers["Authorization"] = f"Bearer {settings.national_catalog_auth_token}"

    if not params and "Authorization" not in headers:
        raise NationalCatalogIntegrationError(
            "Не задана авторизация НК: укажите NATIONAL_CATALOG_API_KEY или NATIONAL_CATALOG_AUTH_TOKEN"
        )
    feed_params = dict(params)
    if settings.national_catalog_supplier_key:
        feed_params["supplier_key"] = settings.national_catalog_supplier_key

    last_error: Exception | None = None
    response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=settings.national_catalog_timeout_seconds) as client:
        categories = await _fetch_categories_by_tnved(
            client=client,
            send_url=settings.national_catalog_send_url,
            auth_params=params,
            headers=headers,
            tnved=card.tn_ved,
        )
        _validate_category_access(categories, card.tn_ved, cat_id)

        active_cat_ids = _active_cat_ids_from_categories(
            [c for c in categories if isinstance(c, dict)]
        )
        required_attrs, attrs_resolved_cat_id = await _fetch_required_attrs(
            client=client,
            send_url=settings.national_catalog_send_url,
            auth_params=params,
            headers=headers,
            tnved=card.tn_ved,
            cat_id=cat_id,
            active_cat_ids=active_cat_ids,
        )
        effective_cat_id = cat_id if cat_id is not None else attrs_resolved_cat_id
        _, unresolved_required = _build_required_attrs(card, required_attrs)
        if unresolved_required:
            raise NationalCatalogIntegrationError(
                "Не хватает обязательных атрибутов НК для этой категории/ТН ВЭД. "
                f"Требуются attr_id={unresolved_required}. "
                "Добавьте заполнение этих атрибутов в интеграцию."
            )

        entry_variants = _build_entry_variants(card, effective_cat_id, required_attrs)
        for attempt in range(1, settings.national_catalog_retry_attempts + 1):
            total_variants = len(entry_variants) * 3
            variant_idx = 0
            for entry in entry_variants:
                for request_body in _build_request_bodies(entry):
                    variant_idx += 1
                    try:
                        response = await client.post(
                            settings.national_catalog_send_url,
                            params=feed_params,
                            json=request_body,
                            headers=headers,
                        )
                        if response.status_code in {200, 201, 202}:
                            break
                        response_payload = _serialize_response(response)
                        last_error = NationalCatalogIntegrationError(
                            "Национальный каталог отклонил карточку "
                            f"[attempt={attempt}, variant={variant_idx}/{total_variants}, "
                            f"status={response.status_code}, url={response.request.url}]: "
                            f"{response_payload}; sent_payload={request_body}"
                        )
                    except httpx.HTTPError as exc:
                        last_error = NationalCatalogIntegrationError(
                            "Ошибка запроса в Национальный каталог "
                            f"[attempt={attempt}, variant={variant_idx}/{total_variants}]: {exc}"
                        )
                    if response is not None and response.status_code in {200, 201, 202}:
                        break
                if response is not None and response.status_code in {200, 201, 202}:
                    break
            if response is not None and response.status_code in {200, 201, 202}:
                break

            if attempt < settings.national_catalog_retry_attempts:
                await asyncio.sleep(settings.national_catalog_retry_delay_seconds)

    if response is None or response.status_code not in {200, 201, 202}:
        raise NationalCatalogIntegrationError(str(last_error) if last_error else "Не удалось отправить карточку")

    response_payload = _serialize_response(response)
    feed_id = _extract_feed_id(response_payload)
    remote_status = _resolve_remote_status(response_payload)
    if not feed_id:
        return NationalCatalogSubmissionResult(
            remote_status=remote_status,
            feed_id=None,
            feed_status=None,
            feed_payload=response_payload,
        )

    feed_status, feed_payload = await fetch_feed_status(
        feed_id=feed_id,
        settings_send_url=settings.national_catalog_send_url,
        auth_params=params,
        headers=headers,
        supplier_key=settings.national_catalog_supplier_key,
        timeout_seconds=settings.national_catalog_timeout_seconds,
    )
    return NationalCatalogSubmissionResult(
        remote_status=remote_status,
        feed_id=feed_id,
        feed_status=feed_status,
        feed_payload=feed_payload,
    )
