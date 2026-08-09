from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, urlsplit


BTIH_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
BTIH_BASE32_PATTERN = re.compile(r"^[A-Z2-7]{32}$", re.I)


class InvalidMagnet(ValueError):
    pass


def _normalize_btih(value: str) -> str:
    if BTIH_PATTERN.fullmatch(value):
        return value.lower()
    if BTIH_BASE32_PATTERN.fullmatch(value):
        try:
            return base64.b32decode(value.upper()).hex()
        except ValueError as exc:
            raise InvalidMagnet("BTIH 特征码无效") from exc
    raise InvalidMagnet("请输入完整 magnet 或 40 位十六进制/32 位 Base32 特征码")


def normalize_magnet(uri_or_hash: str) -> tuple[str, str]:
    value = uri_or_hash.strip()
    if BTIH_PATTERN.fullmatch(value) or BTIH_BASE32_PATTERN.fullmatch(value):
        info_hash = _normalize_btih(value)
        return f"magnet:?xt=urn:btih:{info_hash}", info_hash
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "magnet":
        raise InvalidMagnet("请输入完整 magnet 或有效的 BTIH 特征码")
    exact_topics = parse_qs(parsed.query).get("xt", [])
    btih = next(
        (topic.removeprefix("urn:btih:") for topic in exact_topics if topic.lower().startswith("urn:btih:")),
        "",
    )
    try:
        info_hash = _normalize_btih(btih)
    except InvalidMagnet as exc:
        raise InvalidMagnet("magnet 缺少有效的 BTIH") from exc
    return value, info_hash


def magnet_info_hash(uri_or_hash: str) -> str:
    return normalize_magnet(uri_or_hash)[1]
