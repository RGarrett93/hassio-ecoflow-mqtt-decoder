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
