"""HTTP API views for the signal notification system."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import threading
from datetime import datetime
from typing import Any, Dict, Tuple

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from observability.models import SignalGroup, UserSlackMap
from observability.services.grouping import SignalPayload, SignalService
from observability.services.slack_connector import SlackConnector

signal_service = SignalService(notifier=SlackConnector())
IDEMPOTENCY_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
IDEMPOTENCY_LOCK = threading.Lock()
IDEMPOTENCY_TTL_SECONDS = 600


def _authorized(request: HttpRequest) -> bool:
    token = getattr(settings, "INTERNAL_INGEST_TOKEN", "")
    if not token:
        return True
    header = request.headers.get("Authorization", "")
    return header == f"Bearer {token}"


def _serialize_group(group: SignalGroup) -> Dict[str, Any]:
    return {
        "id": str(group.id),
        "status": group.status,
        "current_severity": group.current_severity,
        "tenant_id": group.tenant_id,
        "tenant_code": group.tenant_code,
        "job_name": group.job_name,
        "signal_type": group.signal_type,
        "first_seen_at": group.first_seen_at.isoformat(),
        "last_seen_at": group.last_seen_at.isoformat(),
        "count_total": group.count_total,
        "count_24h": group.count_24h,
        "assigned_to_user_id": group.assigned_to_user_id,
        "assigned_team_id": group.assigned_team_id,
        "acknowledged_at": group.acknowledged_at.isoformat() if group.acknowledged_at else None,
        "ui_url": group.ui_url,
        "slack_channel_id": group.slack_channel_id,
        "slack_root_ts": group.slack_root_ts,
    }


@csrf_exempt
def ingest_signal(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not _authorized(request):
        return HttpResponse(status=401)

    raw_body = request.body.decode("utf-8") or "{}"
    body = json.loads(raw_body)
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        with IDEMPOTENCY_LOCK:
            cached = IDEMPOTENCY_CACHE.get(idempotency_key)
        now_ts = time.time()
        if cached and now_ts - cached[0] < IDEMPOTENCY_TTL_SECONDS:
            return JsonResponse(cached[1], status=200)

    payload = SignalPayload(
        tenant_id=body["tenant_id"],
        tenant_code=body["tenant_code"],
        job_name=body["job_name"],
        source=body["source"],
        signal_type=body["signal_type"],
        severity=int(body["severity"]),
        summary=body["summary"],
        details_json=body.get("details_json", {}),
        occurred_at=_parse_datetime(body.get("occurred_at")),
        run_id=body.get("run_id"),
        task_id=body.get("task_id"),
        stage=body.get("stage"),
        error_class=body.get("error_class"),
        error_message=body.get("error_message"),
    )
    signal, group = signal_service.ingest_signal(payload)
    response_payload = {
        "signal_id": str(signal.id),
        "signal_group_id": str(group.id),
        "signal_group_status": group.status,
        "fingerprint": signal.fingerprint,
    }
    if idempotency_key:
        with IDEMPOTENCY_LOCK:
            IDEMPOTENCY_CACHE[idempotency_key] = (time.time(), response_payload)
    return JsonResponse(response_payload, status=201)


def list_signal_groups(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    groups = signal_service.list_groups(
        status=request.GET.get("status"),
        assigned_to=request.GET.get("assigned_to"),
        tenant_id=request.GET.get("tenant_id"),
        job_name=request.GET.get("job_name"),
        severity=int(request.GET.get("severity")) if request.GET.get("severity") else None,
        updated_since=_parse_datetime(request.GET.get("updated_since")),
        search=request.GET.get("search"),
    )
    return JsonResponse({"results": [_serialize_group(g) for g in groups]})


def get_signal_group(request: HttpRequest, group_id: str) -> HttpResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    detail = signal_service.group_detail(group_id)
    return JsonResponse(
        {
            "group": _serialize_group(detail["group"]),
            "recent_signals": [
                {
                    "id": str(sig.id),
                    "occurred_at": sig.occurred_at.isoformat(),
                    "severity": sig.severity,
                    "summary": sig.summary,
                }
                for sig in detail["recent_signals"]
            ],
            "activities": [
                {
                    "action": act.action,
                    "created_at": act.created_at.isoformat(),
                    "actor_type": act.actor_type,
                    "actor_user_id": act.actor_user_id,
                    "metadata_json": act.metadata_json,
                }
                for act in detail["activities"]
            ],
        }
    )


@csrf_exempt
def acknowledge_group(request: HttpRequest, group_id: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = json.loads(request.body.decode("utf-8") or "{}")
    actor_user_id = body.get("actor_user_id") or "unknown"
    group = signal_service.acknowledge_group(group_id, actor_user_id)
    return JsonResponse(_serialize_group(group))


@csrf_exempt
def snooze_group(request: HttpRequest, group_id: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = json.loads(request.body.decode("utf-8") or "{}")
    until = _parse_datetime(body.get("snoozed_until")) or timezone.now()
    actor_user_id = body.get("actor_user_id")
    group = signal_service.snooze_group(group_id, until, actor_user_id)
    return JsonResponse(_serialize_group(group))


@csrf_exempt
def assign_group(request: HttpRequest, group_id: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = json.loads(request.body.decode("utf-8") or "{}")
    group = signal_service.assign_group(group_id, body.get("user_id"), body.get("team_id"))
    return JsonResponse(_serialize_group(group))


@csrf_exempt
def close_group(request: HttpRequest, group_id: str) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    body = json.loads(request.body.decode("utf-8") or "{}")
    actor_user_id = body.get("actor_user_id")
    group = signal_service.close_group(group_id, actor_user_id)
    return JsonResponse(_serialize_group(group))


@csrf_exempt
def slack_interactions(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not _verify_slack_signature(request):
        return HttpResponse(status=401)

    payload_raw = request.POST.get("payload") or request.body.decode("utf-8")
    payload = json.loads(payload_raw)
    actions = payload.get("actions", [])
    for action in actions:
        if action.get("action_id") == "signal_group_ack":
            group_id = action.get("value")
            slack_user_id = payload.get("user", {}).get("id")
            mapping = UserSlackMap.objects.filter(slack_user_id=slack_user_id).first()
            actor_user_id = mapping.user_id if mapping else slack_user_id
            if group_id:
                signal_service.acknowledge_group(group_id, actor_user_id or "unknown")
            break
    return JsonResponse({"ok": True})


def _verify_slack_signature(request: HttpRequest) -> bool:
    signing_secret = getattr(settings, "SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        return True
    signature = request.headers.get("X-Slack-Signature", "")
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    if not signature or not timestamp:
        return False
    body = request.body.decode("utf-8")
    basestring = f"v0:{timestamp}:{body}".encode("utf-8")
    computed = "v0=" + hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None
