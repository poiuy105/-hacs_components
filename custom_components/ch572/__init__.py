"""CH572 BatteryGuard 集成入口。

每台 CH572 设备一个 config entry（unique_id 为 MAC）。HA 独占设备：首次连接自动
生成 appId 完成绑定，之后自动认证。绑定凭证持久化在 config entry 的 data 里。
"""
import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import CH572DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SWITCH, Platform.EVENT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """建立连接 + 绑定握手，失败让 HA 重试。"""
    address: str = entry.data[CONF_ADDRESS]

    if not bluetooth.async_ble_device_from_address(hass, address, connectable=True):
        raise ConfigEntryNotReady(
            f"CH572 {address} 不在任何可连接适配器/代理范围内"
        )

    coordinator = CH572DataUpdateCoordinator(hass, entry, address)
    entry.runtime_data = coordinator

    try:
        await coordinator.async_setup()
    except Exception as err:
        raise ConfigEntryNotReady(f"无法连接/绑定 {address}: {err}") from err

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载集成，断开连接。"""
    coordinator: CH572DataUpdateCoordinator = entry.runtime_data
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await coordinator.async_shutdown()
    return unloaded
