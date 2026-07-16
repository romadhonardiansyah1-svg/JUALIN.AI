"""
WhatsApp Cloud API provider.
"""
import hmac
import hashlib
import re
import httpx

from config import get_settings
from services.messaging.base import MessagingProvider, ParsedInboundMessage, SendMessageResult

_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
_LANGUAGE_RE = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")


class WhatsAppCloudProvider(MessagingProvider):
    provider_name = "whatsapp_cloud"
    # Declared provider capabilities — do not invent idempotency/reconcile headers.
    supports_idempotency = False
    supports_reconcile = False

    def __init__(self, access_token: str = "", phone_number_id: str = "", app_secret: str = "", waba_id: str = ""):
        settings = get_settings()
        self.access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.app_secret = app_secret or settings.WHATSAPP_APP_SECRET
        self.waba_id = waba_id or getattr(settings, "WHATSAPP_WABA_ID", "") or ""
        self.graph_version = settings.WHATSAPP_GRAPH_VERSION

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _classify_http_result(self, response: httpx.Response, data: dict) -> SendMessageResult:
        if not response.is_success:
            return SendMessageResult(
                success=False,
                error_message=str(data),
                raw=data,
                # HTTP failure alone is not authoritative rejection evidence.
                outcome="unknown",
            )
        message_id = (data.get("messages") or [{}])[0].get("id", "")
        if not isinstance(message_id, str) or not message_id.strip():
            return SendMessageResult(
                success=False,
                error_message="Provider response did not include a message id",
                raw=data,
                outcome="unknown",
            )
        return SendMessageResult(
            success=True,
            provider_message_id=message_id,
            raw=data,
            outcome="accepted",
        )

    @staticmethod
    def validate_template_send(
        *,
        template_name: str,
        language_code: str,
        body_parameters: list[str] | None,
        expected_parameter_count: int | None,
    ) -> str | None:
        """Return error code if template send inputs are invalid."""
        if not isinstance(template_name, str) or not _TEMPLATE_NAME_RE.match(template_name):
            return "invalid_template_name"
        if not isinstance(language_code, str) or not _LANGUAGE_RE.match(language_code):
            return "invalid_template_language"
        params = body_parameters or []
        if not isinstance(params, list) or any(not isinstance(p, str) for p in params):
            return "invalid_template_parameters"
        if expected_parameter_count is not None and len(params) != expected_parameter_count:
            return "template_parameter_count_mismatch"
        return None

    async def send_message(self, to: str, text: str) -> SendMessageResult:
        if not self.access_token or not self.phone_number_id:
            return SendMessageResult(
                success=False,
                error_message="WhatsApp Cloud API belum dikonfigurasi",
                outcome="unknown",
            )

        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text[:4096]},
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
            data = response.json() if response.text else {}
            return self._classify_http_result(response, data)
        except Exception as e:
            return SendMessageResult(
                success=False,
                error_message=str(e),
                outcome="unknown",
            )

    async def send_template(
        self,
        to: str,
        *,
        template_name: str,
        language_code: str = "id",
        body_parameters: list[str] | None = None,
        expected_parameter_count: int | None = None,
    ) -> SendMessageResult:
        """
        P4.4 — Send an exact approved utility template via WhatsApp Cloud API.

        Parameter order/count is validated client-side. Provider approval status
        must be checked by the caller before invoking this method.
        """
        if not self.access_token or not self.phone_number_id:
            return SendMessageResult(
                success=False,
                error_message="WhatsApp Cloud API belum dikonfigurasi",
                outcome="unknown",
            )

        validation_error = self.validate_template_send(
            template_name=template_name,
            language_code=language_code,
            body_parameters=body_parameters,
            expected_parameter_count=expected_parameter_count,
        )
        if validation_error:
            return SendMessageResult(
                success=False,
                error_message=validation_error,
                outcome="rejected",
            )

        components = []
        params = body_parameters or []
        if params:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p[:1024]} for p in params],
                }
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components,
            },
        }
        url = f"https://graph.facebook.com/{self.graph_version}/{self.phone_number_id}/messages"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, headers=self._headers(), json=payload)
            data = response.json() if response.text else {}
            return self._classify_http_result(response, data)
        except Exception as e:
            return SendMessageResult(
                success=False,
                error_message=str(e),
                outcome="unknown",
            )

    async def sync_message_templates(self) -> dict:
        """
        Fetch provider template list when WABA credentials are available.
        Returns structured result; never invents approved status.
        """
        if not self.access_token or not self.waba_id:
            return {
                "ok": False,
                "error": "provider_credentials_unavailable",
                "templates": [],
                "graph_version": self.graph_version,
            }
        url = (
            f"https://graph.facebook.com/{self.graph_version}/{self.waba_id}/message_templates"
            f"?limit=100&fields=name,language,status,category,id"
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=self._headers())
            data = response.json() if response.text else {}
            if not response.is_success:
                return {
                    "ok": False,
                    "error": "provider_sync_failed",
                    "templates": [],
                    "graph_version": self.graph_version,
                    "http_status": response.status_code,
                }
            items = []
            for row in data.get("data") or []:
                items.append(
                    {
                        "provider_template_id": str(row.get("id") or ""),
                        "name": row.get("name") or "",
                        "language": row.get("language") or "",
                        "status": (row.get("status") or "").lower(),
                        "category": (row.get("category") or "").lower(),
                    }
                )
            return {
                "ok": True,
                "templates": items,
                "graph_version": self.graph_version,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": "provider_sync_exception",
                "error_type": type(e).__name__,
                "templates": [],
                "graph_version": self.graph_version,
            }

    async def send_media(self, to: str, media_url: str, caption: str = "") -> SendMessageResult:
        text = f"{caption}\n{media_url}".strip()
        return await self.send_message(to, text)

    def verify_webhook(self, payload: dict | bytes, headers: dict | None = None) -> bool:
        if not self.app_secret:
            return False
        signature = (headers or {}).get("x-hub-signature-256", "")
        if not signature.startswith("sha256="):
            return False
        raw_payload = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            raw_payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(
            signature.encode("utf-8"),
            f"sha256={expected}".encode("ascii"),
        )

    def parse_webhook(self, payload: dict, headers: dict | None = None) -> list[ParsedInboundMessage]:
        parsed: list[ParsedInboundMessage] = []
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value", {}) or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id", "")
                contacts = {c.get("wa_id"): c for c in value.get("contacts", []) or []}
                for msg in value.get("messages", []) or []:
                    wa_id = msg.get("from", "")
                    profile = (contacts.get(wa_id) or {}).get("profile") or {}
                    content_type = msg.get("type", "text")
                    content = ""
                    if content_type == "text":
                        content = (msg.get("text") or {}).get("body", "")
                    elif content_type in ("image", "document", "audio", "video"):
                        content = (msg.get(content_type) or {}).get("id", "")
                    else:
                        content = str(msg.get(content_type) or msg)
                    parsed.append(ParsedInboundMessage(
                        provider=self.provider_name,
                        channel_external_id=phone_number_id,
                        contact_external_id=wa_id,
                        external_message_id=msg.get("id", ""),
                        phone=wa_id,
                        name=profile.get("name") or "Customer",
                        content=content,
                        content_type=content_type,
                        raw=msg,
                    ))
        return parsed

    def parse_statuses(self, payload: dict) -> list[dict]:
        """
        P1.3 — Parse delivery statuses (not discarded).
        Returns list of normalized status facts with composite identity.
        """
        statuses = []
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value", {}) or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id", "")
                for st in value.get("statuses", []) or []:
                    # Normalize allowlisted fields
                    normalized = {
                        "provider": self.provider_name,
                        "provider_account_id": phone_number_id,
                        "message_id": st.get("id", ""),
                        "status": st.get("status", ""),
                        "timestamp": st.get("timestamp", ""),
                        "recipient_id": st.get("recipient_id", ""),
                    }
                    # Keep minimal raw for audit but not full payload with PII
                    statuses.append(normalized)
        return statuses

    async def health_check(self) -> dict:
        return {
            "provider": self.provider_name,
            "configured": bool(self.access_token and self.phone_number_id),
        }
