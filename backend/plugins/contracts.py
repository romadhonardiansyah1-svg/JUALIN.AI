"""
Plugin contracts for external providers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderHealth:
    provider: str
    enabled: bool
    healthy: bool
    detail: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderPlugin(ABC):
    provider_type: str
    provider_name: str

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        raise NotImplementedError


class PaymentPlugin(ProviderPlugin):
    provider_type = "payment"


class MessagingPlugin(ProviderPlugin):
    provider_type = "messaging"


class ShippingPlugin(ProviderPlugin):
    provider_type = "shipping"


class LLMPlugin(ProviderPlugin):
    provider_type = "llm"
