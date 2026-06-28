"""CH572 BatteryGuard 集成的常量定义。"""

# 集成域名
DOMAIN = "ch572"

# 设备广播名（用于蓝牙匹配发现）
DEVICE_NAME = "CH572_BatteryGuard"

# ---------- GATT UUID（与固件一致）----------
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
# CHAR1: 写入命令（绑定/认证/控制）
CHAR_WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
# CHAR4: notify（继电器状态 / 绑定结果 / 按键事件）
CHAR_NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"

# ---------- 写命令（写 CHAR1，首字节）----------
CMD_RELAY_ON = 0x01
CMD_RELAY_OFF = 0x02
CMD_QUERY_STATUS = 0x03
CMD_BIND = 0x10   # [0x10] + appId[16]
CMD_AUTH = 0x11   # [0x11] + appId[16]
CMD_UNBIND = 0x12

# appId 长度（16 字节 = 128bit）
APP_ID_LEN = 16

# ---------- CHAR4 notify 值（单字节）----------
# 继电器状态
NOTIFY_RELAY_OFF = 0x00
NOTIFY_RELAY_ON = 0x01
# 绑定握手结果
NOTIFY_BIND_OK = 0xA0
NOTIFY_BIND_FAIL = 0xA1
NOTIFY_AUTH_OK = 0xA2
NOTIFY_AUTH_FAIL = 0xA3
# 按键事件
NOTIFY_KEY_SHORT = 0xB0
NOTIFY_KEY_DOUBLE = 0xB2
NOTIFY_KEY_LONG = 0xB1

# ---------- event 实体的事件类型 ----------
EVENT_SHORT_PRESS = "short_press"
EVENT_DOUBLE_PRESS = "double_press"
EVENT_LONG_PRESS = "long_press"

# ---------- 配置字段 ----------
CONF_ADDRESS = "address"
CONF_APP_ID = "app_id"   # 持久化的绑定凭证（16 字节，hex 字符串）

# 默认名称
DEFAULT_NAME = "BatteryGuard"

# ---------- LED 控制命令 ----------
CMD_LED_COLOR = 0x20
CMD_LED_BRIGHTNESS = 0x21
CMD_LED_BREATHE = 0x22
CMD_LED_OFF = 0x23

LED_COLOR_OFF = 0
LED_COLOR_RED = 1
LED_COLOR_GREEN = 2
LED_COLOR_BLUE = 3
LED_COLOR_YELLOW = 4
LED_COLOR_CYAN = 5
LED_COLOR_WHITE = 6
LED_COLOR_PURPLE = 7

BREATHE_SPEED_SLOW = 0
BREATHE_SPEED_MEDIUM = 1
BREATHE_SPEED_FAST = 2

NOTIFY_LED_OK = 0xC0
NOTIFY_LED_ERR = 0xCF
