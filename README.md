# Broadlink AC

Control Broadlink-based air conditioners directly from Home Assistant.

This integration is based on [broadlink_ac_mqtt](https://github.com/liaan/broadlink_ac_mqtt)
but does not require MQTT.

## Installation

### Via [HACS](https://hacs.xyz/)

<a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=jav1x&repository=broadlink-ac&category=integration" target="_blank"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open a repository inside the Home Assistant Community Store." /></a>

## Configuration

<a href="https://my.home-assistant.io/redirect/config_flow_start?domain=broadlink_ac" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>

## Supported features

- HVAC modes: off, auto, cool, heat, dry, fan only
- Target temperature
- Fan modes: auto, low, medium, high, turbo, mute
- Vertical swing modes: top, middle1, middle2, middle3, bottom, swing, auto
- Display switch

### Manual install

Copy the `custom_components/broadlink_ac` directory from this repository into
your Home Assistant `config/custom_components/broadlink_ac` directory, restart
Home Assistant, then use the **Add integration** button or add it from the UI.

## Configuration

1. Restart Home Assistant.
2. Open **Settings → [Integrations](https://my.home-assistant.io/redirect/integrations/)**.
3. Add **Broadlink AC**.
4. Enter one or more local IP addresses of the air conditioners. Separate
   multiple addresses with commas, spaces, or new lines.

The MAC address is optional when adding one device. The integration tries to
discover it automatically by IP. If discovery is blocked on your network, add
devices one at a time and enter the MAC manually in one of these formats:

- `34:ea:34:f7:58:66`
- `34:EA:34:F7:58:66`
- `34ea34f75866`

To add more air conditioners later, open the configured **Broadlink AC**
integration, choose **Configure**, and enter one or more additional IP
addresses.

## Actions

This integration does not register custom Home Assistant actions (services).
Control the air conditioner through the created entities:

- `climate.*` for HVAC control
- `switch.*` for the front panel display