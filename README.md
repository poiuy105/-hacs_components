# piouy105 HACS Components

Home Assistant 自定义集成集合（通过 HACS 安装）。每个集成位于 `custom_components/<domain>/` 下。

## 包含的集成

### CH572 BatteryGuard (`custom_components/ch572/`)

将 WCH CH572 BLE 设备（继电器灯 + 按键）接入 Home Assistant。

**功能：**
- `switch` 实体：继电器灯开关（双向状态同步）
- `event` 实体：按键短按 / 长按（解绑）事件
- 蓝牙自动发现（广播名 `CH572_BatteryGuard`）
- 1对1 互斥绑定（HA 独占设备，首次连接自动绑定）
- 支持多台设备（按 MAC 区分）
- 走 HA 蓝牙后端（ESP32 代理 / 本机适配器均可）

**前置条件：**
- Home Assistant 2024.7+
- 已启用 `bluetooth` 集成（蓝牙代理或本机蓝牙）
- CH572 固件需支持 1对1 绑定协议（CHAR1 写 `0x10/0x11/0x12`，CHAR4 notify `0xA0~0xA3`/`0xB0/0xB1`）

**安装：** 在 HACS 添加本仓库为"集成"类型，或手动把 `custom_components/ch572/` 拷到 HA 的 `custom_components/` 后重启。

**首次添加：** 确保设备处于未绑定状态（新烧录或长按设备 3 秒解绑），HA 发现后添加即自动完成绑定。
