"""
Small provider registry. Disabled providers are omitted instead of crashing app startup.
"""
from collections.abc import Iterable

from plugins.contracts import ProviderPlugin, ProviderHealth


class PluginRegistry:
    def __init__(self):
        self._plugins: dict[tuple[str, str], ProviderPlugin] = {}

    def register(self, plugin: ProviderPlugin, enabled: bool = True) -> None:
        if not enabled:
            return
        self._plugins[(plugin.provider_type, plugin.provider_name)] = plugin

    def get(self, provider_type: str, provider_name: str) -> ProviderPlugin | None:
        return self._plugins.get((provider_type, provider_name))

    def list(self, provider_type: str | None = None) -> Iterable[ProviderPlugin]:
        for (registered_type, _), plugin in self._plugins.items():
            if provider_type is None or registered_type == provider_type:
                yield plugin

    async def health_checks(self) -> list[ProviderHealth]:
        checks: list[ProviderHealth] = []
        for plugin in self._plugins.values():
            try:
                checks.append(await plugin.health_check())
            except Exception as exc:
                checks.append(ProviderHealth(provider=plugin.provider_name, enabled=True, healthy=False, detail=str(exc)))
        return checks


registry = PluginRegistry()
