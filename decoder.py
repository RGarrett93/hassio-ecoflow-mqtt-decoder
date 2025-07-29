import json
import re
import time
import threading
from pathlib import Path
import logging
import paho.mqtt.client as mqtt
from ecoflow_pb2 import HeaderMessage, InverterHeartbeat, setMessage, setHeader, setValue, SendMsgHart, SupplyPriorityPack, BatLowerPack, BatUpperPack, BrightnessPack
from google.protobuf.message import DecodeError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class EcoflowDecoder:
    def __init__(self):
        options_path = Path("/data/options.json")
        options = json.loads(options_path.read_text()) if options_path.exists() else {}
        self.mqtt_host = options.get("mqtt_host", "core-mosquitto")
        self.mqtt_port = options.get("mqtt_port", 1883)
        self.mqtt_user = options.get("mqtt_user", "")
        self.mqtt_password = options.get("mqtt_password", "")
        self.topic = "/sys/75/+/thing/protobuf/upstream"
        self.heartbeats, self.last_seen, self.last_limit_value = {}, {}, {}
        self.offline_timeout, self.discovery_interval, self.heartbeat_interval = 300, 300, 30
        self.heartbeat_logging = options.get("heartbeat_logging", False)
        self.control_logging = options.get("control_logging", False)
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        if self.mqtt_user:
            self.client.username_pw_set(self.mqtt_user, self.mqtt_password)
        self.client.on_connect, self.client.on_message = self.on_connect, self.on_message

    def start(self):
        logging.info(f"Connecting to MQTT broker {self.mqtt_host}:{self.mqtt_port}...")
        self.client.connect(self.mqtt_host, self.mqtt_port, 60)
        self.client.loop_start()
        threading.Thread(target=self.loop_discovery, daemon=True).start()
        threading.Thread(target=self.loop_offline_check, daemon=True).start()
        threading.Thread(target=self.loop_heartbeat, daemon=True).start()
        while True: time.sleep(1)

    def loop_discovery(self):
        while True: time.sleep(self.discovery_interval); self.republish_discovery()

    def loop_offline_check(self):
        while True: time.sleep(60); self.check_device_offline()

    def loop_heartbeat(self):
        while True: time.sleep(self.heartbeat_interval); self.send_inverter_heartbeat()

    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        logging.info(f"Connected to MQTT broker (reason_code={reason_code})")
        client.subscribe(self.topic)
        client.subscribe("homeassistant/number/+/set")
        client.subscribe("homeassistant/select/+/set")
        client.message_callback_add("homeassistant/number/+/set", self.on_number_update)
        client.message_callback_add("homeassistant/select/+/set", self.on_supply_mode_change)

    def on_number_update(self, client, userdata, msg):
        topic, payload = msg.topic, msg.payload.decode()
        if "_battery_lower_limit/set" in topic: self.on_lower_limit_change(client, userdata, msg)
        elif "_battery_upper_limit/set" in topic: self.on_upper_limit_change(client, userdata, msg)
        elif "_inverter_brightness/set" in topic: self.on_brightness_change(client, userdata, msg)
        else: self.on_slider_change_raw(client, userdata, msg)

    def on_message(self, client, userdata, msg):
        try:
            if not msg.payload:
                return logging.info("Empty payload received.")
            message = HeaderMessage()
            message.ParseFromString(msg.payload)
            for header in message.header:
                if not header.device_sn.startswith("HW51") or header.cmd_id != 1:
                    continue
                heartbeat = InverterHeartbeat()
                heartbeat.ParseFromString(header.pdata)
                if self.heartbeat_logging:
                    logging.info(f"[{header.device_sn}] Decoded heartbeat: {heartbeat}")
                self.heartbeats[header.device_sn] = heartbeat
                self.last_seen[header.device_sn] = time.time()
                self.publish_heartbeat(header.device_sn, heartbeat)
        except DecodeError as e:
            logging.info(f"Decode error: {e}")

    def republish_discovery(self):
        logging.info("Republishing MQTT discovery for all known EcoFlow devices...")
        for sn, hb in self.heartbeats.items(): self.publish_heartbeat(sn, hb)

    def check_device_offline(self):
        now = time.time()
        for sn, last in list(self.last_seen.items()):
            if now - last > self.offline_timeout:
                logging.info(f"{sn} is offline. Forcing zero state.")
                self.publish_heartbeat(sn, InverterHeartbeat(), force_zero=True)

    def send_inverter_heartbeat(self):
        for sn in self.heartbeats:
            hb = SendMsgHart(
                link_id=15, 
                src=32, 
                dest=53, 
                d_src=1, 
                d_dest=1, 
                enc_type=0, 
                check_type=0, 
                cmd_func=32, 
                cmd_id=10, 
                data_len=2, 
                need_ack=1, 
                is_ack=0, 
                ack_type=0, 
                seq=int(time.time()))
            self.client.publish(f"/sys/75/{sn}/thing/property/cmd", hb.SerializeToString())
            if self.heartbeat_logging:         
                logging.info(f"Sent inverter heartbeat to {sn}")

    def publish_heartbeat(self, device_sn, hb, force_zero=False):
        short_name = f"ps{device_sn[-4:].lower()}"
        last4 = device_sn[-4:].lower()

        # Human-readable names for fields
        field_names = {
            "inv_error_code": "Inverter Error Code",
            "inv_warning_code": "Inverter Warning Code",
            "pv1_error_code": "PV1 Error Code",
            "pv1_warning_code": "PV1 Warning Code",
            "pv2_error_code": "PV2 Error Code",
            "pv2_warning_code": "PV2 Warning Code",
            "bat_error_code": "Battery Error Code",
            "bat_warning_code": "Battery Warning Code",
            "llc_error_code": "LLC Error Code",
            "llc_warning_code": "LLC Warning Code",
            "wireless_error_code": "Wireless Error Code",
            "wireless_warning_code": "Wireless Warning Code",
            "pv1_status": "PV1 Status",
            "pv2_status": "PV2 Status",
            "bat_status": "Battery Status",
            "llc_status": "LLC Status",
            "inv_status": "Inverter Status",
            "pv1_input_volt": "PV1 Input Voltage",
            "pv1_op_volt": "PV1 Operating Voltage",
            "pv1_input_cur": "PV1 Input Current",
            "pv1_input_watts": "PV1 Input Power",
            "pv1_temp": "PV1 Temperature",
            "pv2_input_volt": "PV2 Input Voltage",
            "pv2_op_volt": "PV2 Operating Voltage",
            "pv2_input_cur": "PV2 Input Current",
            "pv2_input_watts": "PV2 Input Power",
            "pv2_temp": "PV2 Temperature",
            "bat_input_volt": "Battery Input Voltage",
            "bat_op_volt": "Battery Operating Voltage",
            "bat_input_cur": "Battery Input Current",
            "bat_input_watts": "Battery Input Power",
            "bat_temp": "Battery Temperature",
            "bat_soc": "Battery State of Charge",
            "llc_input_volt": "LLC Input Voltage",
            "llc_op_volt": "LLC Operating Voltage",
            "llc_temp": "LLC Temperature",
            "inv_input_volt": "Inverter Input Voltage",
            "inv_op_volt": "Inverter Operating Voltage",
            "inv_output_cur": "Inverter Output Current",
            "inv_output_watts": "Inverter Output Power",
            "inv_temp": "Inverter Temperature",
            "inv_freq": "Inverter Frequency",
            "inv_dc_cur": "Inverter DC Current",
            "bp_type": "Battery Pack Type",
            "inv_relay_status": "Inverter Relay Status",
            "pv1_relay_status": "PV1 Relay Status",
            "pv2_relay_status": "PV2 Relay Status",
            "install_country": "Installation Country",
            "install_town": "Installation Town",
            "permanent_watts": "Permanent Power",
            "dynamic_watts": "Dynamic Power",
            "supply_priority": "Supply Priority",
            "lower_limit": "Discharge Limit",
            "upper_limit": "Charge Limit",
            "inv_on_off": "Inverter On/Off",
            "inv_brightness": "Inverter Brightness",
            "heartbeat_frequency": "Heartbeat Frequency",
            "rated_power": "Rated Power",
            "battery_charge_remain": "Battery Charge Remaining",
            "battery_discharge_remain": "Battery Discharge Remaining"
        }

        base_topic = f"homeassistant/sensor/ecoflow_{short_name}"
        online_topic = f"homeassistant/binary_sensor/ecoflow_{short_name}_online"
        mode_topic = f"homeassistant/select/ecoflow_{short_name}_supply_mode/state"
        mode_value = "Prioritize power supply" if hb.supply_priority == 0 else "Prioritize power storage"
        initial = int(hb.permanent_watts / 10) if not force_zero else 0
        self.last_limit_value[device_sn] = initial

        # Convert raw brightness (0–1023) to percentage for HA
        brightness_percent = 0
        if hasattr(hb, "inv_brightness"):
            brightness_percent = int((hb.inv_brightness / 1023.0) * 100)

        # Online sensor configuration
        config_online = {
            "name": "Online",
            "state_topic": f"{online_topic}/state",
            "unique_id": f"ecoflow_{last4}_online",
            "device_class": "connectivity",
            "payload_on": "ON",
            "payload_off": "OFF",
            "device": {
                "identifiers": [f"ecoflow_{short_name}"],
                "manufacturer": "EcoFlow",
                "model": "PowerStream",
                "name": f"EcoFlow PS{device_sn[-4:]}"
            }
        }
        self.client.publish(f"{online_topic}/config", json.dumps(config_online), retain=True)
        self.client.publish(f"{online_topic}/state", "OFF" if force_zero else "ON", retain=True)
        self.client.publish(mode_topic, mode_value, retain=True)

        # Field definitions including all InverterHeartbeat fields, with scaling and warnings/errors disabled by default
        fields = {
            "inv_error_code": (hb.inv_error_code, None),
            "inv_warning_code": (hb.inv_warning_code, None),
            "pv1_error_code": (hb.pv1_error_code, None),
            "pv1_warning_code": (hb.pv1_warning_code, None),
            "pv2_error_code": (hb.pv2_error_code, None),
            "pv2_warning_code": (hb.pv2_warning_code, None),
            "bat_error_code": (hb.bat_error_code, None),
            "bat_warning_code": (hb.bat_warning_code, None),
            "llc_error_code": (hb.llc_error_code, None),
            "llc_warning_code": (hb.llc_warning_code, None),
            "wireless_error_code": (hb.wireless_error_code, None),
            "wireless_warning_code": (hb.wireless_warning_code, None),
            "pv1_status": (hb.pv1_status, None),
            "pv2_status": (hb.pv2_status, None),
            "bat_status": (hb.bat_status, None),
            "llc_status": (hb.llc_status, None),
            "inv_status": (hb.inv_status, None),
            "pv1_input_volt": (hb.pv1_input_volt / 10.0, "V"),
            "pv1_op_volt": (hb.pv1_op_volt / 100.0, "V"),
            "pv1_input_cur": (hb.pv1_input_cur / 10.0, "A"),
            "pv1_input_watts": (hb.pv1_input_watts / 10.0, "W"),
            "pv1_temp": (hb.pv1_temp / 10.0, "°C"),
            "pv2_input_volt": (hb.pv2_input_volt / 10.0, "V"),
            "pv2_op_volt": (hb.pv2_op_volt / 100.0, "V"),
            "pv2_input_cur": (hb.pv2_input_cur / 10.0, "A"),
            "pv2_input_watts": (hb.pv2_input_watts / 10.0, "W"),
            "pv2_temp": (hb.pv2_temp / 10.0, "°C"),
            "bat_input_volt": (hb.bat_input_volt / 10.0, "V"),
            "bat_op_volt": (hb.bat_op_volt / 10.0, "V"),
            "bat_input_cur": (hb.bat_input_cur / 10.0, "A"),
            "bat_input_watts": (hb.bat_input_watts / 10.0, "W"),
            "bat_temp": (hb.bat_temp / 10.0, "°C"),
            "bat_soc": (hb.bat_soc, "%"),
            "llc_input_volt": (hb.llc_input_volt / 10.0, "V"),
            "llc_op_volt": (hb.llc_op_volt / 100.0, "V"),
            "llc_temp": (hb.llc_temp / 10.0, "°C"),
            "inv_input_volt": (hb.inv_input_volt / 100.0, "V"),
            "inv_op_volt": (hb.inv_op_volt / 10.0, "V"),
            "inv_output_cur": (hb.inv_output_cur / 1000.0, "A"),
            "inv_output_watts": (hb.inv_output_watts / 10.0, "W"),
            "inv_temp": (hb.inv_temp / 10.0, "°C"),
            "inv_freq": (hb.inv_freq / 10.0, "Hz"),
            "inv_dc_cur": (hb.inv_dc_cur / 1000.0, "A"),
            "bp_type": (hb.bp_type, None),
            "inv_relay_status": (hb.inv_relay_status, None),
            "pv1_relay_status": (hb.pv1_relay_status, None),
            "pv2_relay_status": (hb.pv2_relay_status, None),
            "install_country": (hb.install_country, None),
            "install_town": (hb.install_town, None),
            "permanent_watts": (hb.permanent_watts / 10.0, "W"),
            "dynamic_watts": (hb.dynamic_watts / 10.0, "W"),
            "supply_priority": (hb.supply_priority, None),
            "lower_limit": (hb.lower_limit, "%"),
            "upper_limit": (hb.upper_limit, "%"),
            "inv_on_off": (hb.inv_on_off, None),
            "inv_brightness": (brightness_percent, "%"),
            "heartbeat_frequency": (hb.heartbeat_frequency, "s"),
            "rated_power": (hb.rated_power / 10.0, "W"),
            "battery_charge_remain": (hb.battery_charge_remain, "Wh"),
            "battery_discharge_remain": (hb.battery_discharge_remain, "Wh")
        }

        device_classes = {
            "V": "voltage",
            "mV": "voltage",
            "A": "current",
            "W": "power",
            "Wh": "energy",
            "%": "battery",
            "C": "temperature",
            "Hz": "frequency",
            "s": "duration"
        }

        # When publishing MQTT discovery, mark all error and warning code entities as disabled by default.
        hidden_entities = [k for k in fields.keys() if "error_code" in k or "warning_code" in k or "status" in k]

        # Publish each sensor
        for key, (value, unit) in fields.items():
            config_topic = f"{base_topic}/{key}/config"
            state_topic = f"{base_topic}/{key}/state"
            config_payload = {
                "name": field_names.get(key, key.replace('_', ' ').title()),
                "state_topic": state_topic,
                "unique_id": f"ecoflow_{last4}_{key}",
                "device": {
                    "identifiers": [f"ecoflow_{short_name}"],
                    "manufacturer": "EcoFlow",
                    "model": "PowerStream",
                    "name": f"EcoFlow PS{device_sn[-4:]}"
                }
            }
            if unit:
                config_payload["unit_of_measurement"] = unit
                if unit in device_classes:
                    config_payload["device_class"] = device_classes[unit]
            if key in hidden_entities:
                config_payload["enabled_by_default"] = False
            self.client.publish(config_topic, json.dumps(config_payload), retain=True)
            self.client.publish(state_topic, "0" if force_zero else str(value), retain=True)

        # Power limit control
        limit_topic = f"homeassistant/number/ecoflow_{short_name}_power_limit/config"
        limit_payload = {
            "name": "Power Limit",
            "min": 0,
            "max": 800,
            "step": 1,
            "mode": "box",
            "state_topic": f"homeassistant/number/ecoflow_{short_name}_power_limit/state",
            "command_topic": f"homeassistant/number/ecoflow_{short_name}_power_limit/set",
            "unique_id": f"ecoflow_{last4}_power_limit",
            "device": {
                "identifiers": [f"ecoflow_{short_name}"],
                "manufacturer": "EcoFlow",
                "model": "PowerStream",
                "name": f"EcoFlow PS{device_sn[-4:]}"
            }
        }
        self.client.publish(limit_topic, json.dumps(limit_payload), retain=True)
        self.client.publish(limit_payload["state_topic"], str(initial), retain=True)

        # Supply mode select
        select_topic = f"homeassistant/select/ecoflow_{short_name}_supply_mode/config"
        select_payload = {
            "name": "Power Supply Mode",
            "options": ["Prioritize power supply", "Prioritize power storage"],
            "state_topic": f"homeassistant/select/ecoflow_{short_name}_supply_mode/state",
            "command_topic": f"homeassistant/select/ecoflow_{short_name}_supply_mode/set",
            "unique_id": f"ecoflow_{last4}_supply_priority",
            "device": {
                "identifiers": [f"ecoflow_{short_name}"],
                "manufacturer": "EcoFlow",
                "model": "PowerStream",
                "name": f"EcoFlow PS{device_sn[-4:]}"
            }
        }
        self.client.publish(select_topic, json.dumps(select_payload), retain=True)

        # Battery lower limit slider
        lower_topic = f"homeassistant/number/ecoflow_{short_name}_battery_lower_limit/config"
        lower_payload = {
            "name": "Battery Discharge Limit",
            "min": 0,
            "max": 30,
            "step": 1,
            "mode": "box",
            "state_topic": f"homeassistant/number/ecoflow_{short_name}_battery_lower_limit/state",
            "command_topic": f"homeassistant/number/ecoflow_{short_name}_battery_lower_limit/set",
            "unique_id": f"ecoflow_{last4}_battery_lower_limit",
            "device": {
                "identifiers": [f"ecoflow_{short_name}"],
                "manufacturer": "EcoFlow",
                "model": "PowerStream",
                "name": f"EcoFlow PS{device_sn[-4:]}"
            },
            "unit_of_measurement": "%"
        }
        self.client.publish(lower_topic, json.dumps(lower_payload), retain=True)
        self.client.publish(lower_payload["state_topic"], str(hb.lower_limit if not force_zero else 0), retain=True)

        # Battery upper limit slider
        upper_topic = f"homeassistant/number/ecoflow_{short_name}_battery_upper_limit/config"
        upper_payload = {
            "name": "Battery Charge Limit",
            "min": 50,
            "max": 100,
            "step": 1,
            "mode": "box",
            "state_topic": f"homeassistant/number/ecoflow_{short_name}_battery_upper_limit/state",
            "command_topic": f"homeassistant/number/ecoflow_{short_name}_battery_upper_limit/set",
            "unique_id": f"ecoflow_{last4}_battery_upper_limit",
            "device": {
                "identifiers": [f"ecoflow_{short_name}"],
                "manufacturer": "EcoFlow",
                "model": "PowerStream",
                "name": f"EcoFlow PS{device_sn[-4:]}"
            },
            "unit_of_measurement": "%"
        }
        self.client.publish(upper_topic, json.dumps(upper_payload), retain=True)
        self.client.publish(upper_payload["state_topic"], str(hb.upper_limit if not force_zero else 0), retain=True)

        # Brightness slider
        bright_topic = f"homeassistant/number/ecoflow_{short_name}_inverter_brightness/config"
        bright_payload = {
            "name": "Inverter Brightness",
            "min": 0,
            "max": 100,
            "step": 1,
            "mode": "box",
            "state_topic": f"homeassistant/number/ecoflow_{short_name}_inverter_brightness/state",
            "command_topic": f"homeassistant/number/ecoflow_{short_name}_inverter_brightness/set",
            "unique_id": f"ecoflow_{last4}_inverter_brightness",
            "device": {
                "identifiers": [f"ecoflow_{short_name}"],
                "manufacturer": "EcoFlow",
                "model": "PowerStream",
                "name": f"EcoFlow PS{device_sn[-4:]}"
            },
            "unit_of_measurement": "%"
        }
        self.client.publish(bright_topic, json.dumps(bright_payload), retain=True)
        self.client.publish(
            bright_payload["state_topic"],
            str(brightness_percent if not force_zero else 0),
            retain=True
        )

    def on_slider_change_raw(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        match = re.match(r"homeassistant/number/ecoflow_(.+)_power_limit/set", topic)
        if not match:
            return

        short_name = match.group(1)
        # Reconstruct full device_sn from heartbeats dict keys (find match by last 4 chars)
        device_sn = next((sn for sn in self.heartbeats if sn.endswith(short_name[-4:].upper())), None)
        if not device_sn or not device_sn.startswith("HW51"):
            return
        if self.control_logging:
            logging.info(f"Received MQTT power limit update for {device_sn} via {short_name}: {payload}")

        try:
            watts = int(float(payload))
            deci_watts = max(0, watts * 10)

            last_value = self.last_limit_value.get(device_sn)
            if last_value == watts:
                if self.control_logging:
                    logging.info(f"Power limit {watts}W unchanged for {device_sn}, skipping.")
                return

            self.last_limit_value[device_sn] = watts

            val = setValue(value=deci_watts)
            pdata_bytes = val.SerializeToString()

            msg = setMessage(
                header=setHeader(
                    pdata=pdata_bytes,
                    src=32,
                    dest=53,
                    d_src=1,
                    d_dest=1,
                    check_type=3,
                    cmd_func=20,
                    cmd_id=129,
                    data_len=len(pdata_bytes),
                    need_ack=1,
                    seq=int(time.time()),
                    version=19,
                    payload_ver=1,
                    **{"from": "ios"},
                    device_sn=device_sn
                )
            )

            topic = f"/sys/75/{device_sn}/thing/property/cmd"
            self.client.publish(topic, msg.SerializeToString())
            if self.control_logging:
                logging.info(f"Sent power limit {watts}W ({deci_watts} deciwatts) to {device_sn}")
        except Exception as e:
            logging.info(f"Failed to send power limit command for {device_sn}: {e}")

    def on_supply_mode_change(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()

        match = re.match(r"homeassistant/select/ecoflow_(.+)_supply_mode/set", topic)
        if not match:
            return
        short_name = match.group(1)

        # Find full device_sn from short_name (e.g., ps140)
        device_sn = None
        for sn in self.heartbeats.keys():
            if sn.lower().endswith(short_name[-4:]):
                device_sn = sn
                break

        if not device_sn or not device_sn.startswith("HW51"):
            return

        value = 0 if payload == "Prioritize power supply" else 1
        if self.control_logging:
            logging.info(f"Received supply mode change for {short_name} ({device_sn}): {payload} -> {value}")

        try:
            pack = SupplyPriorityPack(supply_priority=value)
            pdata_bytes = pack.SerializeToString()

            header = setHeader(
                src=32,
                dest=53,
                d_src=1,
                d_dest=1,
                check_type=3,
                cmd_func=20,
                cmd_id=130,
                data_len=len(pdata_bytes),
                need_ack=1,
                seq=int(time.time()),
                version=19,
                payload_ver=1,
                **{"from": "ios"},
                device_sn=device_sn
            )
            object.__setattr__(header, "pdata", pdata_bytes)

            msg_out = setMessage(header=header)
            topic = f"/sys/75/{device_sn}/thing/property/cmd"
            self.client.publish(topic, msg_out.SerializeToString())
            if self.control_logging:
                logging.info(f"Sent raw SupplyPriorityPack ({value}) to {short_name} ({device_sn})")

        except Exception as e:
            logging.info(f"Failed to send supply priority command for {short_name} ({device_sn}): {e}")

    def on_lower_limit_change(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        match = re.match(r"homeassistant/number/ecoflow_(.+)_battery_lower_limit/set", topic)
        if not match:
            return
        short_name = match.group(1)

        # Resolve short_name (e.g., ps140) back to full device_sn
        device_sn = None
        for sn in self.heartbeats.keys():
            if sn.lower().endswith(short_name[-4:]):
                device_sn = sn
                break

        if not device_sn or not device_sn.startswith("HW51"):
            return

        try:
            value = int(float(payload))
            pack = BatLowerPack(lower_limit=value)
            pdata_bytes = pack.SerializeToString()

            msg_out = setMessage(
                header=setHeader(
                    pdata=pdata_bytes,
                    src=32,
                    dest=53,
                    d_src=1,
                    d_dest=1,
                    check_type=3,
                    cmd_func=20,
                    cmd_id=132,  # WN511_SET_BAT_LOWER_PACK
                    data_len=len(pdata_bytes),
                    need_ack=1,
                    seq=int(time.time()),
                    version=19,
                    payload_ver=1,
                    **{"from": "ios"},
                    device_sn=device_sn
                )
            )
            topic = f"/sys/75/{device_sn}/thing/property/cmd"
            self.client.publish(topic, msg_out.SerializeToString())
            if self.control_logging:
                logging.info(f"Sent Battery Lower Limit {value}% to {short_name} ({device_sn})")
        except Exception as e:
            logging.info(f"Failed to send Battery Lower Limit for {short_name} ({device_sn}): {e}")

    def on_upper_limit_change(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        match = re.match(r"homeassistant/number/ecoflow_(.+)_battery_upper_limit/set", topic)
        if not match:
            return
        short_name = match.group(1)

        # Resolve short_name (e.g., ps140) back to full device_sn
        device_sn = None
        for sn in self.heartbeats.keys():
            if sn.lower().endswith(short_name[-4:]):
                device_sn = sn
                break

        if not device_sn or not device_sn.startswith("HW51"):
            return

        try:
            value = int(float(payload))
            pack = BatUpperPack(upper_limit=value)
            pdata_bytes = pack.SerializeToString()

            msg_out = setMessage(
                header=setHeader(
                    pdata=pdata_bytes,
                    src=32,
                    dest=53,
                    d_src=1,
                    d_dest=1,
                    check_type=3,
                    cmd_func=20,
                    cmd_id=133,  # WN511_SET_BAT_UPPER_PACK
                    data_len=len(pdata_bytes),
                    need_ack=1,
                    seq=int(time.time()),
                    version=19,
                    payload_ver=1,
                    **{"from": "ios"},
                    device_sn=device_sn
                )
            )
            topic = f"/sys/75/{device_sn}/thing/property/cmd"
            self.client.publish(topic, msg_out.SerializeToString())
            if self.control_logging:
                logging.info(f"Sent Battery Upper Limit {value}% to {short_name} ({device_sn})")
        except Exception as e:
            logging.info(f"Failed to send Battery Upper Limit for {short_name} ({device_sn}): {e}")

    def on_brightness_change(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode()
        match = re.match(r"homeassistant/number/ecoflow_(.+)_inverter_brightness/set", topic)
        if not match:
            return
        short_name = match.group(1)

        # Resolve short_name (e.g., ps140) back to full device_sn
        device_sn = None
        for sn in self.heartbeats.keys():
            if sn.lower().endswith(short_name[-4:]):
                device_sn = sn
                break

        if not device_sn or not device_sn.startswith("HW51"):
            return

        try:
            percent = int(float(payload))
            # Scale 0–100% → 0–1023 (inverter bits)
            scaled_value = int((percent / 100.0) * 1023)

            pack = BrightnessPack(brightness=scaled_value)
            pdata_bytes = pack.SerializeToString()

            msg_out = setMessage(
                header=setHeader(
                    pdata=pdata_bytes,
                    src=32,
                    dest=53,
                    d_src=1,
                    d_dest=1,
                    check_type=3,
                    cmd_func=20,
                    cmd_id=135,  # WN511_SET_BRIGHTNESS_PACK
                    data_len=len(pdata_bytes),
                    need_ack=1,
                    seq=int(time.time()),
                    version=19,
                    payload_ver=1,
                    **{"from": "ios"},
                    device_sn=device_sn
                )
            )
            topic = f"/sys/75/{device_sn}/thing/property/cmd"
            self.client.publish(topic, msg_out.SerializeToString())
            if self.control_logging:
                logging.info(f"Sent Brightness {percent}% ({scaled_value} bits) to {short_name} ({device_sn})")
        except Exception as e:
            logging.info(f"Failed to send Brightness for {short_name} ({device_sn}): {e}")

if __name__ == "__main__":
    decoder = EcoflowDecoder()
    decoder.start()
