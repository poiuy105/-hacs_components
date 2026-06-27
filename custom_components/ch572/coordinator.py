"""CH572 运行时协调器。

轻量容器（不轮询）：持有 CH572Device，把 CHAR4 notify 分发给注册的实体，
并在绑定成功时把 appId 持久化到 config entry。
"""
import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_APP_ID, DEFAULT_NAME, DOMAIN
from .device import CH572Device

_LOGGER = logging.getLogger(__name__)


class CH572DataUpdateCoordinator(DataUpdateCoordinator[None]):
    """CH572 运行时容器。"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, address: str) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self.address = address

        app_id_hex: str = entry.data.get(CONF_APP_ID, "")
        app_id = bytes.fromhex(app_id_hex) if app_id_hex else None

        self.device = CH572Device(
            hass,
            address,
            app_id,
            on_notify=self._dispatch_notify,
            on_app_id_persisted=self._persist_app_id,
        )
        self._notify_callbacks: list[Callable[[int], None]] = []

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.unique_id or self.address)},
            name=f"{DEFAULT_NAME} {self._short()}",
            manufacturer="WCH",
            model="CH572 BatteryGuard",
        )

    def _short(self) -> str:
        parts = self.address.replace("-", ":").split(":")
        if len(parts) >= 2:
            return f"{parts[-2].upper()}{parts[-1].upper()}"
        return self.address

    def register_notify_callback(self, cb: Callable[[int], None]) -> Callable[[], None]:
        """实体注册 notify 回调，返回取消函数。"""
        self._notify_callbacks.append(cb)

        def _remove() -> None:
            if cb in self._notify_callbacks:
                self._notify_callbacks.remove(cb)

        return _remove

    @callback
    def _dispatch_notify(self, byte_val: int) -> None:
        for cb in list(self._notify_callbacks):
            cb(byte_val)

    @callback
    def _persist_app_id(self, app_id_hex: str) -> None:
        """绑定成功后把 appId 写回 config entry（下次重连走认证）。"""
        data = dict(self.entry.data)
        data[CONF_APP_ID] = app_id_hex
        self.hass.async_create_task(self._async_persist(data))

    async def _async_persist(self, data: dict) -> None:
        await self.hass.config_entries.async_update_entry(self.entry, data=data)
        _LOGGER.info("%s: 已持久化绑定 appId", self.address)

    async def async_setup(self) -> None:
        await self.device.start()

    async def async_shutdown(self) -> None:
        await self.device.stop()

    async def _async_update_data(self) -> None:
        # 不轮询，状态由 notify 推送
        return None
