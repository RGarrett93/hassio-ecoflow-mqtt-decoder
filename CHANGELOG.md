# Changelog

## v1.0.7
### Fix
- Prevented “online blip” while devices are offline by avoiding state republish when no recent heartbeat traffic has been received.
- Eliminated Home Assistant MQTT number range errors while offline (e.g. `battery_charge_limit` min 50) by no longer publishing out-of-range `0` states.
- Improved offline handling by using MQTT availability so entities become `unavailable` instead of being force-zeroed.

### Notes
- No breaking changes.
- Existing entity IDs and discovery topics remain the same; only offline/availability behavior changed.

## v1.0.6
### Fix
- `battery_charge_remain` device class and unit of measurement corrected.
- `battery_discharge_remain` device class and unit of measurement corrected.
### Notes
- No breaking changes.

## v1.0.5
### Fix
- `deci_watts` preventing  0W from being sent, thanks @RudolfRendier.

### Notes
- No breaking changes.

## v1.0.4
### Added
- `control_logging` configuration option to enable or disable verbose logging of commands sent (disabled by default).

### Notes
- Minor update to include control_logging.

## v1.0.3
### Added
- `heartbeat_logging` configuration option to enable or disable verbose logging of decoded heartbeats (disabled by default).
- Improved compatibility with `paho-mqtt` by switching to the v2 API to remove the deprecation warning.

### Notes
- No breaking changes.
- Default behavior is unchanged; logs are quieter unless explicitly enabled via `heartbeat_logging`.
