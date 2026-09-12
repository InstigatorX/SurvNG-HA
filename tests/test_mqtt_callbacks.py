"""Exercise HA's MQTT/timer job dispatch, including its executor classification."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HassJob, HassJobType, HomeAssistant

from custom_components.survng.mqtt import SurvNGMqttState, async_subscribe_state


def test_mqtt_and_expiry_update_all_cameras_on_event_loop(tmp_path) -> None:
    async def run():
        hass = HomeAssistant(str(tmp_path))
        hass.config.components.add("mqtt")
        loop_thread = threading.get_ident()
        state = SurvNGMqttState()
        entry = SimpleNamespace(data={})
        updates = []
        def update():
            assert threading.get_ident() == loop_thread
            updates.append(tuple(state.objects))

        coordinator = SimpleNamespace(async_update_listeners=update)
        subscribe = AsyncMock(return_value=Mock())
        timers = []

        def schedule(_hass, delay, action):
            assert threading.get_ident() == loop_thread
            timers.append((delay, action))
            return Mock()

        # Only stub MQTT registration; dispatch uses Home Assistant's actual jobs.
        mqtt_module = SimpleNamespace(async_subscribe=subscribe)
        with patch("homeassistant.components.mqtt", mqtt_module, create=True), patch(
            "homeassistant.helpers.event.async_call_later", schedule
        ):
            unsubscribers = await async_subscribe_state(hass, entry, state, coordinator)
            receive = subscribe.call_args_list[0].args[2]
            job = HassJob(receive)
            assert job.job_type is HassJobType.Callback
            for camera_id in ("gate", "front-door", "lower-garage"):
                hass.async_run_hass_job(job, SimpleNamespace(
                    topic=f"survng/camera/{camera_id}/object", payload='{"classes":["person"]}',
                ))
            assert updates[-1] == ("gate", "front-door", "lower-garage")
            for delay, action in timers:
                assert delay == 15
                timer_job = HassJob(action)
                assert timer_job.job_type is HassJobType.Callback
                hass.async_run_hass_job(timer_job, None)
            assert len(updates) == 6
            for unsubscribe in unsubscribers:
                unsubscribe()
        await hass.async_block_till_done()

    asyncio.run(run())


def test_native_setup_does_not_wait_for_an_unconfigured_mqtt_integration(tmp_path) -> None:
    async def run():
        hass = HomeAssistant(str(tmp_path))
        assert await async_subscribe_state(hass, SimpleNamespace(data={}), SurvNGMqttState(), Mock()) == []
        await hass.async_block_till_done()
    asyncio.run(run())
