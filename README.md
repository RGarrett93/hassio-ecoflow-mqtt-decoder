# EcoFlow MQTT Decoder Add-on for Home Assistant

This Home Assistant add-on listens to **EcoFlow PowerStream** MQTT traffic, decodes Protobuf messages, and republishes the data as standard Home Assistant entities using MQTT Discovery.
It also supports **sending control commands** back to PowerStream devices, such as:

* Adjusting **Battery Charge/Discharge Limits**
* Setting **Power Limit** (up to 800 W)
* Controlling **Inverter Brightness**
* Switching **Power Supply Mode** ("Prioritize power supply" or "Prioritize power storage")

This lets you fully monitor and control your PowerStream devices within Home Assistant.

---

## Features

* Automatically discovers EcoFlow PowerStream devices by listening on MQTT.
* Decodes live telemetry (PV input, battery status, inverter data, etc.).
* Exposes all metrics to Home Assistant as MQTT sensors (auto-discovered).
* Publishes online/offline status for each device.
* Supports bidirectional control (send commands to devices via Home Assistant UI).
* Automatically re-publishes discovery topics every 5 minutes (in case HA restarts).
* Handles offline devices by forcing zeroed values if no messages are received for 5 minutes.

---

## Installation

1. Create self TLS certificates for Mosquitto MQTT broker or you can use EMQX addon (Home Assistant Community Add-ons) which will handle that.

2. Use AdGuard or Pi-hole to redirect `mqtt-e.ecoflow.com` to your MQTT broker (your HA IP address).

3. **Optional but recommended** otherwise you have to allow anonymous login to your MQTT broker.
   * Install [MQTT TLS Honeypot Add-on](https://github.com/RGarrett93/hassio-mqtt-honeypot) and run this once, look at the logs and note your Powerstream(s) MQTT credentials.
   * Add the username and password to your MQTT broker.

4. In Home Assistant:

   * Go to **Settings → Add-ons → Add-on Store → ⋮ (three dots) → Repositories**.

5. Find **EcoFlow MQTT Decoder** in the add-on list and install it.

---

## Configuration

The add-on needs to connect to your MQTT broker (it does **not** connect to EcoFlow Cloud).
In the add-on configuration, you must set your MQTT credentials and topic.

Example configuration:

```yaml
mqtt_host: core-mosquitto # Or use a0d7b954-emqx for EMQX
mqtt_port: 1883
mqtt_user: "homeassistant"
mqtt_password: "your_mqtt_password"
```

### Options

| Option          | Type       | Default                             | Description                             |
| --------------- | ---------- | ----------------------------------- | --------------------------------------- |
| `mqtt_host`     | `string`   | `core-mosquitto`                    | Hostname of your MQTT broker.           |
| `mqtt_port`     | `int`      | `1883`                              | MQTT broker port.                       |
| `mqtt_user`     | `string`   | `""`                                | MQTT username (leave blank for none).   |
| `mqtt_password` | `password` | `""`                                | MQTT password            |



---

## Usage

1. Start the add-on from the Supervisor panel.
2. Check the logs — you should see output like:

```
[INFO] Connecting to MQTT broker core-mosquitto:1883...
[INFO] Connected to MQTT broker
[INFO] [HW51ZKH4SF5P1234] Decoded heartbeat: pv1_input_volt: 315 ...
[INFO] Sent inverter heartbeat to HW51ZKH4SF5P1234
```

3. All entities will appear automatically, named like:

   * `sensor.ecoflow_ps1234_pv1_input_volt`
   * `number.ecoflow_ps1234_power_limit`
   * `select.ecoflow_ps1234_supply_mode`
   * `number.ecoflow_ps1234_battery_lower_limit`
   * `number.ecoflow_ps1234_battery_upper_limit`
   * `number.ecoflow_ps1234_inverter_brightness`

4. You can control your PowerStream device by adjusting these sliders/selectors in Home Assistant.
   Changes will be **sent back to the device** over MQTT automatically.

---

## Notes

* Each device is identified by its serial number (`device_sn`). The last 4 characters (e.g., `ps1234`) are used in entity IDs.
* If a device stops reporting for 5 minutes, it is marked as **offline** and its sensor states are reset to zero.
* The add-on does **not** talk to EcoFlow Cloud — it only listens and publishes via **local MQTT** using DNS redirect.

---

## Credits

This project:

* Uses **Google Protobuf** for decoding EcoFlow telemetry.
* Uses **Paho MQTT** for message handling.
* Automatically integrates with Home Assistant via **MQTT Discovery**.
* tolwi [Ecoflow Cloud Integration](https://github.com/tolwi/hassio-ecoflow-cloud)

Many thanks to [Tom Van Dyck](https://github.com/tomvd/) for sharing their findings for local control:
https://github.com/tomvd/local-powerstream
