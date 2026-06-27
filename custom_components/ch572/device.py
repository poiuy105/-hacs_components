"""CH572 设备封装：主动连接、1对1 绑定握手、写命令、订阅 notify、断线重连。

连接走 HA 的蓝牙后端（自动选择 ESP32 代理或本机适配器）：
- BLEDevice 来自 bluetooth.async_ble_device_from_address(connectable=True)
- 连接用 bleak_retry_connector.establish_connection（自带断线重试 + 指数退避）
"""
import asyncio
import logging
import secrets
from collections.abc import Callable
from datetime import timedelta

from bleak import BleakClient, BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback

from .const import (
    APP_ID_LEN,
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    CMD_AUTH,
    CMD_BIND,
    CMD_QUERY_STATUS,
    CMD_RELAY_OFF,
    CMD_RELAY_ON,
    NOTIFY_AUTH_FAIL,
    NOTIFY_AUTH_OK,
    NOTIFY_BIND_FAIL,
    NOTIFY_BIND_OK,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = timedelta(seconds=30)
HANDSHAKE_TIMEOUT = 10  # 握手等待 notify 回复的超时（秒）
RECONNECT_MIN_DELAY = 5
RECONNECT_MAX_DELAY = 300
HEARTBEAT_INTERVAL = 10   # 心跳间隔（秒）
HEARTBEAT_MAX_MISSED = 3  # 连续无响应次数达到此值判离线（≈30s）


class CH572Device:
    """单台 CH572 的 GATT 通信 + 1对1 绑定握手。"""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        app_id: bytes | None,
        on_notify: Callable[[int], None],
        on_app_id_persisted: Callable[[str], None],
        on_connection_state: Callable[[bool], None] | None = None,
    ) -> None:
        self._hass = hass
        self._address = address
        self._app_id = app_id  # 已持久化的 appId；None 表示首次需绑定
        self._on_notify = on_notify
        self._on_app_id_persisted = on_app_id_persisted
        self._on_connection_state = on_connection_state

        self._client: BleakClient | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._stop_requested = False
        self._lock = asyncio.Lock()

        self._authenticated = False
        self._auth_failed = False  # 绑定/认证失败，停止自动重连
        self._handshake_future: asyncio.Future | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_pending = False
        self._heartbeat_missed = 0

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    # ---------- 写命令 ----------
    async def turn_relay_on(self) -> None:
        await self._send(CMD_RELAY_ON)

    async def turn_relay_off(self) -> None:
        await self._send(CMD_RELAY_OFF)

    async def _send(self, cmd: int, payload: bytes = b"") -> None:
        if not self._authenticated:
            _LOGGER.warning("%s: 命令 0x%02X 被忽略（未认证）", self._address, cmd)
            return
        data = bytes([cmd]) + payload
        last_err: Exception | None = None
        for _ in range(3):
            try:
                client = await self._ensure_connected()
                async with self._lock:
                    await client.write_gatt_char(CHAR_WRITE_UUID, data, response=True)
                _LOGGER.debug("%s: wrote %s", self._address, data.hex())
                return
            except (BleakError, asyncio.TimeoutError) as err:
                last_err = err
                await asyncio.sleep(0.5)
        raise BleakError(f"写入失败: {last_err}")

    async def _send_raw(self, cmd: int, payload: bytes = b"") -> None:
        """握手命令，不受 authenticated 限制。"""
        data = bytes([cmd]) + payload
        client = await self._ensure_connected()
        async with self._lock:
            await client.write_gatt_char(CHAR_WRITE_UUID, data, response=True)

    # ---------- 连接管理 ----------
    def _get_ble_device(self) -> BLEDevice | None:
        return bluetooth.async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )

    async def _ensure_connected(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client
        ble_device = self._get_ble_device()
        if ble_device is None:
            raise BleakError(
                f"{self._address} 未被任何可连接适配器/代理发现"
            )
        self._client = await establish_connection(
            BleakClient,
            ble_device,
            self._address,
            disconnected_callback=self._handle_disconnect,
            use_cached_services=True,
        )
        await self._client.start_notify(CHAR_NOTIFY_UUID, self._notification_handler)
        _LOGGER.info("%s: 已连接并订阅 notify", self._address)
        return self._client

    def _handle_disconnect(self, client: BleakClient) -> None:
        _LOGGER.warning("%s: 连接断开", self._address)
        self._set_connection_state(False)
        do_handshake = self._authenticated
        self._authenticated = False
        if self._stop_requested or self._auth_failed:
            return
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(
                self._reconnect_loop(do_handshake)
            )

    async def _reconnect_loop(self, do_handshake: bool) -> None:
        delay = RECONNECT_MIN_DELAY
        while not self._stop_requested and not self._auth_failed:
            try:
                await asyncio.sleep(delay)
                await self._ensure_connected()
                if do_handshake:
                    await self._do_handshake()
                self._set_connection_state(True)
                return
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug(
                    "%s: 重连失败(%s)，%ss 后重试", self._address, err, delay * 2
                )
                delay = min(delay * 2, RECONNECT_MAX_DELAY)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("%s: 重连异常", self._address)
                delay = min(delay * 2, RECONNECT_MAX_DELAY)

    # ---------- notify 处理 ----------
    def _notification_handler(self, _sender: int, data: bytearray) -> None:
        if not data:
            return
        val = data[0]
        _LOGGER.debug("%s: notify 0x%02X", self._address, val)
        # bleak 回调可能在非事件循环线程，marshal 到事件循环再处理
        self._hass.loop.call_soon_threadsafe(self._process_notify, val)

    @callback
    def _process_notify(self, val: int) -> None:
        # 收到任意 notify = 设备在线，重置心跳计数并恢复 available
        self._heartbeat_pending = False
        self._heartbeat_missed = 0
        self._set_connection_state(True)

        if val == NOTIFY_BIND_OK:
            self._authenticated = True
            self._resolve_handshake(True, "bind_ok")
        elif val == NOTIFY_AUTH_OK:
            self._authenticated = True
            self._resolve_handshake(True, "auth_ok")
        elif val == NOTIFY_BIND_FAIL:
            # 设备已被别的客户端绑定 → 停止重连，需在设备上解绑后重新配置
            self._auth_failed = True
            self._resolve_handshake(False, "bind_fail")
        elif val == NOTIFY_AUTH_FAIL:
            # appId 失效（设备端被解绑）→ 清除本地 appId，停止重连，需重新配置
            self._app_id = None
            self._auth_failed = True
            self._resolve_handshake(False, "auth_fail")
        else:
            # 继电器状态(0/1) + 按键事件(0xB0/0xB1) → 转发给实体
            self._on_notify(val)

    def _resolve_handshake(self, ok: bool, reason: str) -> None:
        fut = self._handshake_future
        if fut is not None and not fut.done():
            fut.set_result((ok, reason))

    def _set_connection_state(self, online: bool) -> None:
        """通知上层连接在线状态（用于实体 available）。bleak 回调可能在非事件循环线程，marshal 到事件循环。"""
        if self._on_connection_state:
            self._hass.loop.call_soon_threadsafe(self._on_connection_state, online)

    async def _heartbeat_loop(self) -> None:
        """定期发 query 探活，连续 HEARTBEAT_MAX_MISSED 次无 notify 响应判离线。"""
        while not self._stop_requested:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if self._stop_requested or self._auth_failed:
                continue
            if not self._client or not self._client.is_connected:
                continue
            if self._heartbeat_pending:
                # 上次心跳未收到 notify 响应
                self._heartbeat_missed += 1
                _LOGGER.debug("%s: 心跳无响应 (%d/%d)",
                              self._address, self._heartbeat_missed, HEARTBEAT_MAX_MISSED)
                if self._heartbeat_missed >= HEARTBEAT_MAX_MISSED:
                    self._set_connection_state(False)
            else:
                self._heartbeat_missed = 0
            # 发心跳 query，设备回 relay_state notify
            self._heartbeat_pending = True
            try:
                async with self._lock:
                    await self._client.write_gatt_char(
                        CHAR_WRITE_UUID, bytes([CMD_QUERY_STATUS]), response=True)
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug("%s: 心跳 write 失败: %s", self._address, err)

    # ---------- 绑定握手 ----------
    async def _do_handshake(self) -> tuple[bool, str]:
        is_bind = self._app_id is None
        if is_bind:
            self._app_id = secrets.token_bytes(APP_ID_LEN)

        self._handshake_future = self._hass.loop.create_future()
        cmd = CMD_BIND if is_bind else CMD_AUTH
        try:
            await self._send_raw(cmd, self._app_id)
            ok, reason = await asyncio.wait_for(
                self._handshake_future, timeout=HANDSHAKE_TIMEOUT
            )
        except asyncio.TimeoutError:
            ok, reason = False, "timeout"
        except BleakError as err:
            ok, reason = False, f"write_failed: {err}"
        finally:
            self._handshake_future = None

        if ok and is_bind:
            # 绑定成功 → 持久化 appId，下次重连走认证
            self._on_app_id_persisted(self._app_id.hex())

        if ok:
            _LOGGER.info("%s: 握手成功 (%s)", self._address, reason)
        else:
            self._authenticated = False
            _LOGGER.error("%s: 握手失败 (%s)", self._address, reason)
        return ok, reason

    # ---------- 生命周期 ----------
    async def start(self) -> None:
        self._stop_requested = False
        self._auth_failed = False
        await self._ensure_connected()
        ok, reason = await self._do_handshake()
        if not ok:
            raise BleakError(f"绑定/认证失败: {reason}")
        self._set_connection_state(True)
        # 启动心跳探活
        self._heartbeat_pending = False
        self._heartbeat_missed = 0
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        self._stop_requested = True
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._heartbeat_task = None
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._reconnect_task = None
        if self._client is not None:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
            self._client = None
