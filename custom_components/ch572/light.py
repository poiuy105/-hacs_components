"""CH572 BatteryGuard Light 实体。"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    BREATHE_SPEED_FAST,
    BREATHE_SPEED_MEDIUM,
    BREATHE_SPEED_SLOW,
    DEFAULT_NAME,
    DOMAIN,
    LED_COLOR_BLUE,
    LED_COLOR_CYAN,
    LED_COLOR_GREEN,
    LED_COLOR_OFF,
    LED_COLOR_PURPLE,
    LED_COLOR_RED,
    LED_COLOR_WHITE,
    LED_COLOR_YELLOW,
)
from .coordinator import CH572DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# RGB (0/1) -> LED 颜色编码 映射
_RGB_TO_LED: dict[tuple[int, int, int], int] = {
    (1, 0, 0): LED_COLOR_RED,
    (0, 1, 0): LED_COLOR_GREEN,
    (0, 0, 1): LED_COLOR_BLUE,
    (1, 1, 0): LED_COLOR_YELLOW,
    (0, 1, 1): LED_COLOR_CYAN,
    (1, 1, 1): LED_COLOR_WHITE,
    (1, 0, 1): LED_COLOR_PURPLE,
}

_EFFECT_LIST = ["none", "breathe_slow", "breathe_medium", "breathe_fast"]


def _rgb_to_led_color(r: int, g: int, b: int) -> int:
    """将 0~255 RGB 映射到 7 色编码。阈值 128。"""
    rn = 1 if r > 128 else 0
    gn = 1 if g > 128 else 0
    bn = 1 if b > 128 else 0
    return _RGB_TO_LED.get((rn, gn, bn), LED_COLOR_WHITE)


def _brightness_to_device(brightness: int | None) -> int:
    """HA brightness (0~255) -> 设备 brightness (0~63)。"""
    if brightness is None:
        return 63
    return min(63, max(0, brightness * 63 // 255))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置 Light 实体。"""
    coordinator: CH572DataUpdateCoordinator = entry.runtime_data
    async_add_entities([CH572Light(coordinator)], update_before_add=True)


class CH572Light(LightEntity):
    """CH572 LED 灯实体。"""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = _EFFECT_LIST

    def __init__(self, coordinator: CH572DataUpdateCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_light"
        self._attr_name = "LED 灯"
        self._attr_has_entity_name = True
        self._attr_device_info = coordinator.device_info

        self._color = LED_COLOR_WHITE
        self._brightness = 63
        self._effect = "none"
        self._is_on = False

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int | None:
        """HA brightness 0~255。"""
        if not self._is_on:
            return None
        return self._brightness * 255 // 63

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        if not self._is_on:
            return None
        # 7 色编码 -> RGB (0/255)
        led_r = 255 if self._color in (LED_COLOR_RED, LED_COLOR_YELLOW, LED_COLOR_WHITE, LED_COLOR_PURPLE) else 0
        led_g = 255 if self._color in (LED_COLOR_GREEN, LED_COLOR_YELLOW, LED_COLOR_CYAN, LED_COLOR_WHITE) else 0
        led_b = 255 if self._color in (LED_COLOR_BLUE, LED_COLOR_CYAN, LED_COLOR_WHITE, LED_COLOR_PURPLE) else 0
        return (led_r, led_g, led_b)

    @property
    def effect(self) -> str | None:
        return self._effect if self._is_on else None

    @property
    def available(self) -> bool:
        return self.coordinator.available

    async def async_turn_on(self, **kwargs: Any) -> None:
        """开灯 / 设置颜色 / 亮度 / 效果。"""
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        effect = kwargs.get(ATTR_EFFECT)

        if brightness is not None:
            self._brightness = _brightness_to_device(brightness)

        if rgb is not None:
            self._color = _rgb_to_led_color(*rgb)
            self._is_on = True
            await self.coordinator.device.set_led_color(self._color)
            if self._brightness != 63:
                await self.coordinator.device.set_led_brightness(self._brightness)
        elif effect is not None:
            self._effect = effect
            self._is_on = True
            speed_map = {
                "breathe_slow": BREATHE_SPEED_SLOW,
                "breathe_medium": BREATHE_SPEED_MEDIUM,
                "breathe_fast": BREATHE_SPEED_FAST,
            }
            speed = speed_map.get(effect, BREATHE_SPEED_MEDIUM)
            await self.coordinator.device.set_led_breathe(self._color, speed)
        else:
            # 无参数默认：白光
            self._is_on = True
            self._color = LED_COLOR_WHITE
            await self.coordinator.device.set_led_color(self._color)
            if self._brightness != 63:
                await self.coordinator.device.set_led_brightness(self._brightness)

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """关灯。"""
        self._is_on = False
        await self.coordinator.device.set_led_off()
        self.async_write_ha_state()
