# SurvNG for Home Assistant

Local Home Assistant integration for SurvNG cameras, clean snapshots, live
streams, controls, activity state and incident automations.

## Prerequisites

- Home Assistant 2025.12 or newer.
- A reachable SurvNG URL including its base path. Use the HTTPS endpoint when
  TLS is enabled, for example `https://survng.example.com/survng` (or
  `https://SERVER:8088/survng` for direct access).
- A SurvNG API token with `read` and `camera:control` scopes. Create it in
  **SurvNG → Admin → General → API** and copy the secret when shown.
- Home Assistant MQTT configured if push motion, object and incident events are
  desired. Cameras, snapshots, streams and controls still work through HTTP.

Disable SurvNG's legacy Home Assistant MQTT discovery before enabling this
integration, otherwise Home Assistant will show duplicate devices.

## Install

Copy `custom_components/survng` into Home Assistant's `config/custom_components`
directory and restart Home Assistant. Then open **Settings → Devices & services
→ Add integration**, search for **SurvNG**, and enter the server URL and API
token. HACS custom-repository installation can use this repository's root.

## Behavior

HTTP polling every 30 seconds reconciles authoritative server and camera state.
MQTT supplies low-latency motion, object and incident transitions. Clean camera
images are fetched on demand; live streams use SurvNG's credential-safe go2rtc
descriptor and default to the live/substream. Change the stream or polling
interval in integration options.

Each incident fires a `survng_incident` Home Assistant event containing stable
incident/camera/event IDs, lifecycle state, classes, zones and a link to the
incident page. The page link is intentionally not a direct snapshot API URL:
snapshot endpoints require the bearer token and cannot be safely opened from an
event payload. Image bytes and credentials are never placed on MQTT or the
event bus.

## Troubleshooting

- **Invalid authentication:** create a replacement token with both `read` and
  `camera:control`, then use Home Assistant's reauthentication prompt.
- **TLS certificate error:** Home Assistant verifies HTTPS certificates by
  default. Install the CA that issued a private/self-signed SurvNG certificate
  in the Home Assistant host/container, then keep **Verify TLS certificate**
  enabled. Disable it only on a trusted private network when installing the CA
  is not practical; this weakens protection against man-in-the-middle attacks.
- **Still image works but video does not:** verify Home Assistant can reach the
  RTSP address returned by SurvNG's go2rtc stream-source endpoint.
- **Duplicate devices:** disable legacy MQTT discovery in SurvNG and remove its
  old retained discovery entities.
- **Camera unavailable:** camera power and current-frame availability are
  independent of the SurvNG server's overall availability.

Removing the config entry unsubscribes MQTT listeners and unloads every entity
platform. Removing files alone is not sufficient; remove the entry first.
