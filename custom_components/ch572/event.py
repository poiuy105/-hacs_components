"""CH572 event 实体：按键短按/长按事件，由 CHAR4 notify(0xB0/0xB1) 触发。"""
import logging

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_LONG_PRESS, EVENT_SHORT_PRESS, NOTIFY_KEY_LONG, NOTIFY_KEY_SHORT
from .coordinator import CH572DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up CH572 event entity."""
    coordinator: CH572DataUpdateCoordinator = entry.runtime_data
    async_add_entities([CH572KeyEvent(coordinator, entry.entry_id)])


class CH572KeyEvent(EventEntity):
    """把 CHAR4 的按键 notify 转成 HA event。"""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: CH572DataUpdateCoordinator, entry_id: str) -> None:
        self._coordinator = coordinator
        self.entity_description = EventEntityDescription(
            key="button",
            translation_key="button",
            name="Key",
            # 必须列出所有可能触发的事件类型，否则 _trigger_event 会抛 ValueError
            event_types=[EVENT_SHORT_PRESS, EVENT_LONG_PRESS],
        )
        self._attr_unique_id = f"{entry_id}_key_event"
        self._attr_device_info = coordinator.device_info

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.register_notify_callback(self._on_notify)
        )

    @callback
    def _on_notify(self, byte_val: int) -> None:
        if byte_val == NOTIFY_KEY_SHORT:
            self._trigger_event(EVENT_SHORT_PRESS)
            self.async_write_ha_state()
        elif byte_val == NOTIFY_KEY_LONG:
            self._trigger_event(EVENT_LONG_PRESS)
            self.async_write_ha_state()
