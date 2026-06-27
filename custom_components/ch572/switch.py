"""CH572 switch 实体：继电器灯控制 + CHAR4 notify 状态同步。"""
import logging

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import NOTIFY_RELAY_OFF, NOTIFY_RELAY_ON
from .coordinator import CH572DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CH572 switch entity."""
    coordinator: CH572DataUpdateCoordinator = entry.runtime_data
    async_add_entities([CH572RelaySwitch(coordinator, entry.entry_id)])


class CH572RelaySwitch(SwitchEntity):
    """继电器开关：turn_on/off 写 CHAR1；状态由 CHAR4 notify 同步。"""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: CH572DataUpdateCoordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self.entity_description = SwitchEntityDescription(
            key="relay",
            translation_key="relay",
            name="Relay",
        )
        self._attr_unique_id = f"{entry_id}_relay"
        self._attr_device_info = coordinator.device_info
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.register_notify_callback(self._on_notify)
        )

    @callback
    def _on_notify(self, byte_val: int) -> None:
        if byte_val == NOTIFY_RELAY_ON:
            self._attr_is_on = True
            self.async_write_ha_state()
        elif byte_val == NOTIFY_RELAY_OFF:
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:  # noqa: ANN003
        await self._coordinator.device.turn_relay_on()
        # 乐观更新；真实状态以 CHAR4 notify 回报为准
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:  # noqa: ANN003
        await self._coordinator.device.turn_relay_off()
        self._attr_is_on = False
        self.async_write_ha_state()
