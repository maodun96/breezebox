from pathlib import Path
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import (
    fan,
    sensor,
    text_sensor,
    button,
    select,
    output,
    display,
    font,
    web_server_base,
    esp32,
    ssd1306_base,
    binary_sensor,
    improv_ble,
    ble_client,
)
from esphome.helpers import fnv1_hash_object_id
from esphome.const import CONF_ID

AUTO_LOAD = [
    "json",
    "fan",
    "sensor",
    "text_sensor",
    "button",
    "select",
    "web_server_base",
]
DEPENDENCIES = ["esp32", "web_server", "wifi", "captive_portal"]
ns = cg.esphome_ns.namespace("single_fan")
Controller = ns.class_("Controller", cg.Component)
classes = {
    "fan": ns.class_("ControlFan", fan.Fan),
    "sensor": ns.class_("LocalSensor", sensor.Sensor),
    "text": ns.class_("LocalText", text_sensor.TextSensor),
    "button": ns.class_("ControlButton", button.Button),
    "select": ns.class_("ControlSelect", select.Select),
}
ENTITIES = [
    ("fan", "Main Fan", "风扇", "fan"),
    ("control_mode", "Control Mode", "控制模式", "select"),
    ("temperature", "Temperature", "温度", "sensor"),
    ("humidity", "Humidity", "湿度", "sensor"),
    ("rpm", "Fan Speed", "实际转速", "sensor"),
    ("target_rpm", "Target RPM", "目标转速", "sensor"),
    ("pwm", "PWM Output", "实际输出", "sensor"),
    ("progress", "Calibration Progress", "校准进度", "sensor"),
    ("fault", "Device Fault", "设备故障", "text"),
    ("calibration", "Calibration Status", "校准状态", "text"),
    ("calibrate", "Fan Calibration", "风扇校准", "button"),
    ("cancel", "Cancel Calibration", "取消校准", "button"),
    ("power", "Power On Behavior", "上电行为", "select"),
    ("firmware_version", "Firmware Version", "固件版本", "text"),
]
SCHEMAS = {
    "fan": fan.fan_schema,
    "sensor": sensor.sensor_schema,
    "text": text_sensor.text_sensor_schema,
    "button": button.button_schema,
    "select": select.select_schema,
}
schema = {
    cv.GenerateID(): cv.declare_id(Controller),
    cv.Required("pwm_output"): cv.use_id(output.FloatOutput),
    cv.Required("power_output"): cv.use_id(output.BinaryOutput),
    cv.Required("temperature_source"): cv.use_id(sensor.Sensor),
    cv.Required("humidity_source"): cv.use_id(sensor.Sensor),
    cv.Required("rpm_source"): cv.use_id(sensor.Sensor),
    cv.Required("screen"): cv.use_id(ssd1306_base.SSD1306),
    **{
        cv.Required(name + "_button"): cv.use_id(binary_sensor.BinarySensor)
        for name in ("center", "up", "down", "left", "right")
    },
    cv.Required("sensor_client"): cv.use_id(ble_client.BLEClient),
    cv.Required("provisioning"): cv.use_id(improv_ble.ImprovBLEComponent),
    cv.Required("font"): cv.use_id(font.Font),
    cv.Required("web_server_base_id"): cv.use_id(web_server_base.WebServerBase),
}
for key, en, zh, kind in ENTITIES:
    schema[cv.Optional(key, default={"name": en})] = SCHEMAS[kind](
        classes[kind],
        **(
            {
                "unit_of_measurement": (
                    "°C"
                    if key == "temperature"
                    else "%"
                    if key in ("humidity", "pwm", "progress")
                    else "RPM"
                ),
                "accuracy_decimals": 1 if key == "humidity" else 0,
                "state_class": "measurement",
                **({"device_class": key} if key in ("temperature", "humidity") else {}),
            }
            if kind == "sensor"
            else {}
        ),
    )
CONFIG_SCHEMA = cv.Schema(schema).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    # Translate API display names only; protocol keys and legacy object IDs stay unchanged.
    cases = "".join(
        f'case {fnv1_hash_object_id(config[key]["name"])}u: return ha_english ? "{en}" : "{zh}";'
        for key, en, zh, kind in ENTITIES
    )
    cg.add_global(
        cg.RawStatement(
            "namespace esphome::single_fan { extern bool ha_english; const char *ha_entity_name(uint32_t key) { switch(key) {"
            + cases
            + "default: return nullptr;} } }"
        )
    )
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    for name in [
        "pwm_output",
        "power_output",
        "temperature_source",
        "humidity_source",
        "rpm_source",
        "screen",
        "font",
        "web_server_base_id",
        "center_button",
        "up_button",
        "down_button",
        "left_button",
        "right_button",
        "provisioning",
        "sensor_client",
    ]:
        cg.add(getattr(var, "set_" + name)(await cg.get_variable(config[name])))
    # Keep action IDs stable when entities are added or removed.
    actions = {"control_mode": 1, "calibrate": 11, "cancel": 12, "power": 14}
    for key, en, zh, kind in ENTITIES:
        conf = config[key]
        entity = cg.new_Pvariable(conf[CONF_ID])
        if kind == "fan":
            await fan.register_fan(entity, conf)
        elif kind == "sensor":
            await sensor.register_sensor(entity, conf)
        elif kind == "text":
            await text_sensor.register_text_sensor(entity, conf)
        elif kind == "button":
            await button.register_button(entity, conf)
        elif kind == "select":
            opts = (
                ["Manual Speed", "Automatic Temperature"]
                if key == "control_mode"
                else ["Restore Previous", "Off", "Automatic Temperature"]
            )
            await select.register_select(entity, conf, options=opts)
        if kind in ("fan", "button", "select"):
            cg.add(entity.bind(var, actions.get(key, 0)))
        cg.add(getattr(var, "set_" + key)(entity))
    # Embed the authored, offline page; generation runs only in the selected build directory.
    import gzip

    page = (Path(__file__).resolve().parents[2] / "web" / "index.html").read_bytes()
    data = gzip.compress(page, mtime=0)
    cg.add_global(
        cg.RawStatement(
            "namespace esphome::single_fan { extern const unsigned char WEB_PAGE[] = {"
            + ",".join(map(str, data))
            + "}; extern const size_t WEB_PAGE_SIZE = sizeof(WEB_PAGE); }"
        )
    )
