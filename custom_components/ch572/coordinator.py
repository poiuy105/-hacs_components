"""CH572 运行时协调器。

轻量容器（不轮询）：持有 CH572Device，把 CHAR4 notify 分发给注册的实体，
绑定成功时持久化 appId，并维护设备在线/离线状态（驱动实体 available）。
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

        self._available = False  # 连接建立前视为离线
        self._availability_callbacks: list[Callable[[bool], None]] = []
        self._notify_callbacks: list[Callable[[int], None]] = []

        self.device = CH572Device(
            hass,
            address,
            app_id,
            on_notify=self._dispatch_notify,
            on_app_id_persisted=self._persist_app_id,
            on_connection_state=self.set_available,
        )

    @property
    def available(self) -> bool:
        return self._available

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

    # ---------- notify 分发 ----------
    def register_notify_callback(self, cb: Callable[[int], None]) -> Callable[[], None]:
        self._notify_callbacks.append(cb)

        def _remove() -> None:
            if cb in self._notify_callbacks:
                self._notify_callbacks.remove(cb)

        return _remove

    @callback
    def _dispatch_notify(self, byte_val: int) -> None:
        for cb in list(self._notify_callbacks):
            cb(byte_val)

    # ---------- 在线/离线（驱动实体 available） ----------
    def register_availability_callback(self, cb: Callable[[bool], None]) -> Callable[[], None]:
        self._availability_callbacks.append(cb)

        def _remove() -> None:
            if cb in self._availability_callbacks:
                self._availability_callbacks.remove(cb)

        return _remove

    @callback
    def set_available(self, available: bool) -> None:
        if self._available == available:
            return
        self._available = available
        _LOGGER.info("%s: %s", self.address, "在线" if available else "离线")
        for cb in list(self._availability_callbacks):
            cb(available)

    # ---------- appId 持久化 ----------
    @callback
    def _persist_app_id(self, app_id_hex: str) -> None:
        data = dict(self.entry.data)
        data[CONF_APP_ID] = app_id_hex
        self.hass.async_create_task(self._async_persist(data))

    async def _async_persist(self, data: dict) -> None:
        await self.hass.config_entries.async_update_entry(self.entry, data=data)
        _LOGGER.info("%s: 已持久化绑定 appId", self.address)

    # ---------- 生命周期 ----------
    async def async_setup(self) -> None:
        await self.device.start()

    async def async_shutdown(self) -> None:
        await self.device.stop()

    async def _async_update_data(self) -> None:
        # 不轮询，状态由 notify 推送
        return None
