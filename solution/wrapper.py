"""Observability and mitigation layer for the black-box Observathon agent.

This wrapper keeps the legal boundary: it only calls the agent through call_next,
records telemetry, retries bounded failures, caches repeated requests, and redacts
PII from answers. It does not hardcode answers or read simulator internals.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
from datetime import datetime, timezone

from telemetry.cost import cost_from_usage
from telemetry.redact import redact, redact_value


RETRYABLE_STATUS = {"wrapper_error", "max_steps", "loop"}
LOG_LOCK = threading.Lock()

# Vietnamese number words → int
_VN_NUM = {
    "mot": 1, "một": 1, "hai": 2, "ba": 3, "bon": 4, "bốn": 4,
    "nam": 5, "năm": 5, "sau": 6, "sáu": 6, "bay": 7, "bảy": 7,
    "tam": 8, "tám": 8, "chin": 9, "chín": 9, "muoi": 10, "mười": 10,
}
_VN_NUM_PAT = "|".join(re.escape(k) for k in _VN_NUM)

# Destination keywords for Vietnamese cities/regions
_DEST_KEYWORDS = (
    "giao", "ship", "tới", "den", "đến", "hà nội", "ha noi",
    "hcm", "hồ chí minh", "ho chi minh", "hải phòng", "hai phong",
    "đà nẵng", "da nang", "địa chỉ", "dia chi", "can tho", "cần thơ",
    "vung tau", "vũng tàu", "da lat", "đà lạt",
)


# Transient shipping error codes — retry, not refuse
_TRANSIENT_SHIP_ERRORS = {
    "loyalty_service_down", "service_unavailable", "timeout",
    "rate_limited", "temporary_error",
}

# Regex to strip injected order notes from question before sending to agent
_INJECTION_NOTE_RE = re.compile(
    r'\n?(?:GHI CH[UÚ](?:\s+KH[AÁ]CH)?|Note|P\/S|PS|NOTE)\s*[:\-].*',
    re.IGNORECASE | re.DOTALL,
)
_ORDER_PREFIX_RE = re.compile(r'^ORDER\s*:\s*', re.IGNORECASE)
# PII contact info at end of question (lien he / goi minh qua)
_PII_CONTACT_RE = re.compile(
    r'[.,;]?\s*(?:lien he|liên hệ|goi minh qua|gọi mình qua|gọi tôi qua|lien he email|gọi tẮi)\s*(?:email|sdt|số \u0111t|\u0111iện thoại)?\s*[^.\n]*',
    re.IGNORECASE,
)


def _sanitize_question(question):
    """Strip injected notes, ORDER: prefix and PII contact info before passing to agent.
    Legal per WRAPPER_API.md: 'input sanitize (e.g. strip injected order notes)'.
    """
    text = str(question)
    # Strip ORDER: prefix
    text = _ORDER_PREFIX_RE.sub("", text)
    # Strip injected notes (GHI CHU / Note / P/S sections)
    text = _INJECTION_NOTE_RE.sub("", text)
    # Strip PII contact info (lien he email / goi minh qua sdt)
    text = _PII_CONTACT_RE.sub("", text)
    return text.strip()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _cache_key(question):
    text = re.sub(r"\s+", " ", str(question).strip().lower())
    return "observathon:v1:" + text


def _safe_trace(trace, limit=8):
    if not isinstance(trace, list):
        return []
    return redact_value(trace[:limit])


def _write_jsonl(path, payload):
    line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
    with LOG_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def _log_event(event, context, question, result=None, error=None, attempt=1, wall_ms=0, debug=False):
    result = result or {}
    meta = result.get("meta") or {}
    usage = meta.get("usage") or {}
    answer = result.get("answer")
    _, pii_count = redact(answer or "")
    payload = {
        "ts": _now(),
        "event": event,
        "qid": context.get("qid"),
        "session_id": context.get("session_id"),
        "turn_index": context.get("turn_index"),
        "attempt": attempt,
        "status": result.get("status"),
        "wall_ms": wall_ms,
        "latency_ms": meta.get("latency_ms"),
        "model": meta.get("model"),
        "provider": meta.get("provider"),
        "usage": usage,
        "cost_usd": cost_from_usage(meta.get("model") or "", usage),
        "tools_used": meta.get("tools_used") or [],
        "steps": result.get("steps"),
        "pii_in_answer": pii_count,
        "wrapper_rebuilt_answer": bool(meta.get("wrapper_rebuilt_answer")),
        "wrapper_redactions": int(meta.get("wrapper_redactions") or 0),
        "question_preview": redact(str(question)[:180])[0],
        "trace": _safe_trace(result.get("trace")),
    }
    if error is not None:
        payload["error_type"] = type(error).__name__
        payload["error"] = str(error)
    _write_jsonl("observathon_telemetry.jsonl", payload)
    if error is not None or debug:
        _write_jsonl("wrapper_debug.log", payload)


def _trace_observations(result):
    """Extract per-tool observations from trace, keeping first non-error call."""
    observations = {}
    for item in result.get("trace") or []:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        obs = item.get("observation")
        if tool and isinstance(obs, dict):
            # Keep first valid (non-error) observation for each tool
            if tool in observations and not observations[tool].get("error"):
                continue
            observations[tool] = obs
    return observations


def _extract_quantity(question):
    """
    Robustly extract purchase quantity from Vietnamese question text.
    Returns int or None. Avoids mistaking coupon/discount numbers for quantity.
    """
    text = str(question).lower()

    # Layer 1: Action verb + optional fillers + number/word
    m = re.search(
        r'\b(?:mua|lấy|lay|cho|đặt|dat|ship|order|lấy|đặt)\s+'
        r'(?:mình\s+)?(?:tôi\s+)?(?:hộ\s+)?'
        r'(\d+|' + _VN_NUM_PAT + r')\b',
        text,
    )
    if m:
        v = m.group(1)
        return int(v) if v.isdigit() else _VN_NUM.get(v)

    # Layer 2: Number + (optional unit) + product keyword
    m = re.search(
        r'\b(\d+|' + _VN_NUM_PAT + r')\s+'
        r'(?:cái\s+|chiếc\s+|con\s+|máy\s+|cai\s+|chiec\s+)?'
        r'(?:iphone|ipad|macbook|airpods|samsung|xiaomi|oppo|nokia|sony)\b',
        text,
    )
    if m:
        v = m.group(1)
        return int(v) if v.isdigit() else _VN_NUM.get(v)

    # Layer 3: Fallback — any digit NOT preceded by coupon/discount context
    for m in re.finditer(r'\b(\d+)\b', text):
        prefix = text[max(0, m.start() - 25):m.start()]
        suffix = text[m.end():min(len(text), m.end() + 2)]
        # Skip discount/coupon related numbers
        if any(x in prefix for x in ("giảm ", "giam ", "coupon ", "sale ", "vip", "expired", "winner", "%")):
            continue
        if "%" in suffix:
            continue
        return int(m.group(1))

    return None


def _is_stock_price_question(question):
    """
    Returns True ONLY if the question is asking about stock/price info
    and NOT asking for a purchase total.
    """
    text = str(question).lower()
    asks_stock = any(x in text for x in (
        "con hang", "còn hàng", "con khong", "còn không",
        "het hang", "hết hàng", "stock", "tình trạng",
        "con iphone", "con ipad", "con macbook", "con airpods",
        "con samsung", "con xiaomi",
    ))
    asks_price = any(x in text for x in (
        "gia bao nhieu", "giá bao nhiêu", "gia la bao nhieu",
        "bao nhieu tien", "bao nhiêu tiền",
        "nhieu tien", "nhiêu tiền",
        "don gia", "đơn giá",
        "gia san pham", "giá sản phẩm",
    ))
    asks_total = any(x in text for x in (
        "tong ", "tổng ", "thanh toan", "thanh toán",
        "tong cong", "tổng cộng", "tong tien", "tổng tiền",
        "mua ", "ship ", "giao ", "đặt ", "dat ", "order ",
    ))
    return (asks_stock or asks_price) and not asks_total


def _has_destination(question):
    """Returns True if the question mentions a delivery destination."""
    text = str(question).lower()
    return any(x in text for x in _DEST_KEYWORDS)


def _rebuild_answer_from_trace(result, question):
    """
    Attempt to rebuild answer deterministically from tool observations in trace.
    - For stock/price questions: let LLM answer stand (no total needed).
    - For order questions: compute total exactly from trace data.
    - If data is insufficient (product not found, out of stock, dest unsupported), refuse.
    - NEVER fabricate data not present in trace.
    """
    if not isinstance(result, dict) or result.get("status") != "ok":
        return result

    observations = _trace_observations(result)
    stock = observations.get("check_stock")
    if not isinstance(stock, dict):
        # No stock call made — cannot validate, leave LLM answer as-is
        return result

    # If it's a stock/price-only question, no need to rebuild total
    if _is_stock_price_question(question):
        return result

    found = stock.get("found", False)
    in_stock = stock.get("in_stock", False)
    available = int(stock.get("quantity") or 0)
    unit_price = stock.get("unit_price_vnd")

    qty = _extract_quantity(question)

    # Determine refusal conditions
    should_refuse = False
    if not found or not in_stock:
        should_refuse = True
    elif qty is None or unit_price is None:
        # Cannot compute total deterministically — leave LLM answer
        return result
    elif qty > available:
        should_refuse = True

    if should_refuse:
        rebuilt = "Khong the tinh tong cong."
    else:
        # Shipping
        shipping_obs = observations.get("calc_shipping")
        has_dest = _has_destination(question)

        if has_dest:
            if not isinstance(shipping_obs, dict) or shipping_obs.get("cost_vnd") is None:
                ship_err = (shipping_obs or {}).get("error", "") if isinstance(shipping_obs, dict) else ""
                if ship_err in _TRANSIENT_SHIP_ERRORS:
                    # Transient error: signal wrapper to retry rather than refuse
                    rebuilt = None  # None = retry needed
                else:
                    # Permanent: destination not served
                    rebuilt = "Khong the tinh tong cong."
            else:
                shipping_cost = int(shipping_obs["cost_vnd"])
                discount_obs = observations.get("get_discount") or {}
                pct = int(discount_obs.get("percent") or 0)
                subtotal = int(unit_price) * qty
                discounted = subtotal * (100 - pct) // 100
                total = discounted + shipping_cost
                rebuilt = f"Tong cong: {total} VND"
        else:
            # No destination → shipping = 0
            discount_obs = observations.get("get_discount") or {}
            pct = int(discount_obs.get("percent") or 0)
            subtotal = int(unit_price) * qty
            discounted = subtotal * (100 - pct) // 100
            rebuilt = f"Tong cong: {discounted} VND"

    if rebuilt is None:
        # Transient shipping error — signal caller to retry
        result = copy.deepcopy(result)
        meta = dict(result.get("meta") or {})
        meta["wrapper_needs_retry"] = True
        result["meta"] = meta
        return result

    if rebuilt != result.get("answer"):
        result = copy.deepcopy(result)
        result["answer"] = rebuilt
        meta = dict(result.get("meta") or {})
        meta["wrapper_rebuilt_answer"] = True
        result["meta"] = meta
    return result


def _normalize_answer(answer):
    """Clean up LLM answer: remove markdown, redacted placeholders, fix total format."""
    if not isinstance(answer, str) or not answer:
        return answer
    text = answer.replace("**", "")
    # Remove redacted contact info artifacts
    text = re.sub(r"\s*\([^)]*\[REDACTED(?::[A-Z_]+)?\][^)]*\)", "", text)
    text = re.sub(r"\s*lien he\s*:\s*\[REDACTED(?::[A-Z_]+)?\]\s*", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*Thong tin lien he cua ban[^.\n]*\.", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*Ban co muon dat mua khong\?[^.\n]*\.", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*Neu muon dat hang[^.\n]*\.", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n*Vui long cho biet[^.\n]*\.", "", text, flags=re.IGNORECASE)
    # Normalize total line: remove thousands separators, keep clean integer
    matches = list(re.finditer(r"Tong cong:\s*([0-9][0-9.,\s]*)\s*VND", text, flags=re.IGNORECASE))
    if matches:
        last = matches[-1]
        amount = re.sub(r"\D", "", last.group(1))
        if amount:
            text = text[:last.start()] + f"Tong cong: {amount} VND" + text[last.end():]
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _redact_answer(result, question=None):
    if not isinstance(result, dict):
        return result
    result = _rebuild_answer_from_trace(result, question)
    answer = result.get("answer")
    clean, count = redact(answer or "")
    clean = _normalize_answer(clean)
    if count:
        result = copy.deepcopy(result)
        result["answer"] = clean
        meta = dict(result.get("meta") or {})
        meta["wrapper_redactions"] = count
        result["meta"] = meta
    elif clean != answer:
        result = copy.deepcopy(result)
        result["answer"] = clean
    return result


def _should_retry(result):
    if not isinstance(result, dict):
        return True
    return result.get("status") in RETRYABLE_STATUS


def _needs_retry(result):
    """Check if result needs retry: bad status OR transient shipping error detected."""
    if not isinstance(result, dict):
        return True
    if result.get("status") in RETRYABLE_STATUS:
        return True
    # Transient shipping error flagged by _rebuild_answer_from_trace
    if result.get("meta", {}).get("wrapper_needs_retry"):
        return True
    return False


def mitigate(call_next, question, config, context):
    cache_enabled = bool((config.get("cache") or {}).get("enabled"))
    key = _cache_key(question)

    if cache_enabled:
        with context["cache_lock"]:
            cached = context["cache"].get(key)
        if cached is not None:
            result = copy.deepcopy(cached)
            _log_event("CACHE_HIT", context, question, result=result)
            return result

    retry_conf = config.get("retry") or {}
    max_attempts = int(retry_conf.get("max_attempts", 1) if retry_conf.get("enabled") else 1)
    # Allow at least 2 attempts to handle transient errors (loyalty_service_down etc.)
    max_attempts = max(max_attempts, 2)
    backoff_ms = int(retry_conf.get("backoff_ms", 0))
    last_result = None

    # Sanitize question: strip ORDER: prefix and injected GHI CHU notes
    # before sending to the agent. The original question is preserved for
    # logging and cache keying (full text). This is legal per WRAPPER_API.
    sanitized_q = _sanitize_question(question)

    for attempt in range(1, max(1, max_attempts) + 1):
        t0 = time.time()
        try:
            # Use sanitized question for agent call to avoid injection confusion
            result = call_next(sanitized_q, config)
            wall_ms = int((time.time() - t0) * 1000)
            # Rebuild/validate against original (unsanitized) question for context
            result = _redact_answer(result, sanitized_q)
            _log_event(
                "AGENT_CALL",
                context,
                question,  # log original for observability
                result=result,
                attempt=attempt,
                wall_ms=wall_ms,
                debug=_needs_retry(result),
            )
            last_result = result
            if not _needs_retry(result):
                break
        except Exception as exc:
            wall_ms = int((time.time() - t0) * 1000)
            result = {
                "answer": None,
                "status": "wrapper_error",
                "steps": 0,
                "trace": [],
                "meta": {
                    "latency_ms": wall_ms,
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "tools_used": [],
                    "wrapper_error": f"{type(exc).__name__}: {exc}",
                },
            }
            _log_event("WRAPPER_ERROR", context, question, result=result, error=exc, attempt=attempt, wall_ms=wall_ms)
            last_result = result

        if attempt < max_attempts and _needs_retry(last_result):
            time.sleep(backoff_ms / 1000.0)

    if cache_enabled and isinstance(last_result, dict) and last_result.get("status") == "ok":
        with context["cache_lock"]:
            context["cache"][key] = copy.deepcopy(last_result)

    return last_result
