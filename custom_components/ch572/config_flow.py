"""CH572 BatteryGuard 的配置流程（蓝牙自动发现 + 手动添加）。"""

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback

from .const import DEFAULT_NAME, DEVICE_NAME, DOMAIN


def _format_unique_id(address: str) -> str:
    """MAC 去冒号小写作为 unique_id。"""
    return address.replace(":", "").lower()


def _short_address(address: str) -> str:
    """显示用：取 MAC 末 4 位。"""
    parts = address.replace("-", ":").split(":")
    if len(parts) >= 2:
        return f"{parts[-2].upper()}{parts[-1].upper()}"
    return address


class CH572ConfigFlow(ConfigFlow, domain=DOMAIN):
    """CH572 BatteryGuard 配置流程。"""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_address: str | None = None

    @callback
    def _async_discovered_devices(self) -> list[BluetoothServiceInfoBleak]:
        current = self._async_current_ids(include_ignore=False)
        found: list[BluetoothServiceInfoBleak] = []
        for connectable in (True, False):
            for service_info in async_discovered_service_info(
                self.hass, connectable=connectable
            ):
                if _format_unique_id(service_info.address) in current:
                    continue
                name = service_info.name or service_info.device.name or ""
                if DEVICE_NAME not in name:
                    continue
                found.append(service_info)
        return found

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """蓝牙发现自动触发。"""
        await self.async_set_unique_id(_format_unique_id(discovery_info.address))
        self._abort_if_unique_id_configured()

        name = discovery_info.name or discovery_info.device.name or ""
        if DEVICE_NAME not in name:
            return self.async_abort(reason="not_supported")

        self._discovered_address = discovery_info.address
        self.context["title_placeholders"] = {
            "name": DEFAULT_NAME,
            "address": _short_address(discovery_info.address),
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """弹出“是否添加此设备”确认页。"""
        assert self._discovered_address is not None
        if user_input is not None:
            return self.async_create_entry(
                title=f"{DEFAULT_NAME} {_short_address(self._discovered_address)}",
                data={CONF_ADDRESS: self._discovered_address},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": DEFAULT_NAME,
                "address": _short_address(self._discovered_address),
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """手动添加：从已发现列表里选。"""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(
                _format_unique_id(address), raise_on_progress=False
            )
            self._abort_if_unique_id_configured(updates=CONF_ADDRESS)
            return self.async_create_entry(
                title=f"{DEFAULT_NAME} {_short_address(address)}",
                data={CONF_ADDRESS: address},
            )

        discovered = self._async_discovered_devices()
        if not discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            si.address: f"{DEFAULT_NAME} {_short_address(si.address)}"
                            for si in discovered
                        }
                    )
                }
            ),
        )
