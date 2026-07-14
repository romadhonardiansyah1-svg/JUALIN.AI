"""
WhatsApp Cloud API provider.
"""
import hmac
import hashlib
import httpx

from config import get_settings
from services.messaging.base import MessagingProvider, ParsedInboundMessage, SendMessageResult


class WhatsAppCloudProvider(MessagingProvider):
    provider_name = "whatsapp_cloud"

    def __init__(self, access_token: str = "", phone_number_id: str = "", app_secret: str = ""):
        settings = get_settings()
        self.access_token = access_token or settings.WHATSAPP_ACCESS_TOKEN
        self.phone_number_id = phone_number_id or settings.WHATSAPP_PHONE_NUMBER_ID
        self.app_secret = app_secret or settings.WHATSAPP_APP_SECRET
        self.graph_version = settings.WHATSAPP_GRAPH_VERSION

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def send_message(self, to: str, text: str) -> SendMessageResult:
        if not self.access_token or not self.phone_number_id:
            return SendMessageResult(success=False, error_message="WhatsApp Cloud API belum dikonfigurasi")

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
            if response.status_code >= 400:
                return SendMessageResult(success=False, error_message=str(data), raw=data)
            message_id = (data.get("messages") or [{}])[0].get("id", "")
            return SendMessageResult(success=True, provider_message_id=message_id, raw=data)
        except Exception as e:
            return SendMessageResult(success=False, error_message=str(e))

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
