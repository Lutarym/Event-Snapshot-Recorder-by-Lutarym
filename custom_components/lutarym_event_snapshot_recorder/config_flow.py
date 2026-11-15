"""Einrichtung über die Oberfläche für Event Snapshot Recorder by Lutarym."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAMERA,
    CONF_DOORBELL,
    CONF_RETENTION,
    DEFAULT_RETENTION,
    DOMAIN,
    MAX_RETENTION,
)


def _retention_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=MAX_RETENTION,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="d",
        )
    )


def _camera_selector() -> selector.EntitySelector:
    return selector.EntitySelector(selector.EntitySelectorConfig(domain="camera"))


class DoorbellConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ersteinrichtung."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_DOORBELL])
            self._abort_if_unique_id_configured()
            state = self.hass.states.get(user_input[CONF_DOORBELL])
            title = (
                state.attributes.get("friendly_name", user_input[CONF_DOORBELL])
                if state
                else user_input[CONF_DOORBELL]
            )
            return self.async_create_entry(
                title=title,
                data={CONF_DOORBELL: user_input[CONF_DOORBELL]},
                options={
                    CONF_CAMERA: user_input.get(CONF_CAMERA),
                    CONF_RETENTION: int(user_input[CONF_RETENTION]),
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DOORBELL): selector.EntitySelector(),
                vol.Optional(CONF_CAMERA): _camera_selector(),
                vol.Required(CONF_RETENTION, default=DEFAULT_RETENTION): _retention_selector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DoorbellOptionsFlow()


class DoorbellOptionsFlow(OptionsFlow):
    """Kamera und Speicherdauer nachträglich ändern."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_CAMERA: user_input.get(CONF_CAMERA),
                    CONF_RETENTION: int(user_input[CONF_RETENTION]),
                }
            )

        options = self.config_entry.options
        camera = options.get(CONF_CAMERA)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_CAMERA,
                    description={"suggested_value": camera} if camera else None,
                ): _camera_selector(),
                vol.Required(
                    CONF_RETENTION,
                    default=options.get(CONF_RETENTION, DEFAULT_RETENTION),
                ): _retention_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
