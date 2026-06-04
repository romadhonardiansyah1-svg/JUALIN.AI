"""
Messaging provider contracts for WhatsApp-first inbox.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedInboundMessage:
    provider: str
    channel_external_id: str
    contact_external_id: str
    external_message_id: str
    phone: str
    name: str
    content: str
    content_type: str = "text"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendMessageResult:
    success: bool
    provider_message_id: str = ""
    error_message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class MessagingProvider(ABC):
    provider_name: str

    @abstractmethod
    async def send_message(self, to: str, text: str) -> SendMessageResult:
        ...

    @abstractmethod
    async def send_media(self, to: str, media_url: str, caption: str = "") -> SendMessageResult:
        ...

    @abstractmethod
    def parse_webhook(self, payload: dict, headers: dict | None = None) -> list[ParsedInboundMessage]:
        ...

    @abstractmethod
    def verify_webhook(self, payload: dict, headers: dict | None = None) -> bool:
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        ...
