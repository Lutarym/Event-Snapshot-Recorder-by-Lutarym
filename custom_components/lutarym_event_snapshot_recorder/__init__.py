"""Event Snapshot Recorder by Lutarym.

Speichert jedes Klingeln (nur Drücken, nicht Loslassen), macht dabei ein
Kamerabild, löscht Bilder nach der eingestellten Speicherdauer und stellt
Protokoll und Bilder nur angemeldeten Benutzern bereit.
"""

from __future__ import annotations

from datetime import timedelta
import logging
import os
import re
import shutil
import time
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.camera import async_get_image
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CAMERA,
    CONF_DOORBELL,
    CONF_RETENTION,
    DEFAULT_RETENTION,
    DOMAIN,
    IMAGE_DIR,
    INVALID_STATES,
    LOG_KEEP_DAYS,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

IMAGE_URL = "/api/lutarym_event_snapshot_recorder/image/{entry_id}/{filename}"
FILENAME_RE = re.compile(r"^\d{13}\.jpg$")
ENTRY_ID_RE = re.compile(r"^[A-Za-z0-9]+$")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Websocket Befehl und Bild Adresse einmalig registrieren."""
    hass.data.setdefault(DOMAIN, {})
    websocket_api.async_register_command(hass, ws_presses)
    hass.http.register_view(DoorbellImageView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    doorbell = DoorbellLog(hass, entry)
    await doorbell.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = doorbell
    entry.async_on_unload(doorbell.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Neue Speicherdauer sofort anwenden."""
    doorbell = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if isinstance(doorbell, DoorbellLog):
        await doorbell.async_purge()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Beim Entfernen alle Bilder und das Protokoll löschen."""
    folder = hass.config.path(IMAGE_DIR, entry.entry_id)
    await hass.async_add_executor_job(shutil.rmtree, folder, True)
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


class DoorbellLog:
    """Protokoll und Bilder einer Klingel."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.doorbell: str = entry.data[CONF_DOORBELL]
        self.folder = hass.config.path(IMAGE_DIR, entry.entry_id)
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.presses: list[dict[str, Any]] = []
        self._unsubs: list = []

    @property
    def camera(self) -> str | None:
        return self.entry.options.get(CONF_CAMERA) or None

    @property
    def retention_days(self) -> int:
        return int(self.entry.options.get(CONF_RETENTION, DEFAULT_RETENTION))

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self.presses = (data or {}).get("presses", [])
        await self.hass.async_add_executor_job(os.makedirs, self.folder, 0o700, True)
        await self.async_purge()
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [self.doorbell], self._async_state_changed
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_purge_interval, timedelta(hours=1)
            )
        )

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _async_state_changed(self, event: Event[EventStateChangedData]) -> None:
        old = event.data["old_state"]
        new = event.data["new_state"]
        if new is None or old is None:
            return
        if self.doorbell.startswith("event."):
            # Event Entität: jeder neue gültige Zeitstempel ist ein Klingeln
            pressed = (
                new.state not in INVALID_STATES
                and old.state not in INVALID_STATES
                and new.state != old.state
            )
        else:
            # Nur Drücken (Wechsel auf "on") zählt, Loslassen wird ignoriert
            pressed = new.state == "on" and old.state != "on"
        if pressed:
            self.hass.async_create_task(self._async_record(new.last_changed.timestamp()))

    async def _async_record(self, ts: float) -> None:
        ts_ms = int(ts * 1000)
        # Zeitstempel eindeutig halten, er ist auch der Dateiname des Bildes
        used = {p["ts"] for p in self.presses}
        while ts_ms in used:
            ts_ms += 1
        entry: dict[str, Any] = {"ts": ts_ms, "image": False}
        self.presses.append(entry)
        await self._async_save()

        camera = self.camera
        if not camera:
            return
        try:
            image = await async_get_image(self.hass, camera)
        except HomeAssistantError as err:
            _LOGGER.warning("Kamerabild von %s nicht abrufbar: %s", camera, err)
            return
        path = os.path.join(self.folder, f"{ts_ms}.jpg")
        await self.hass.async_add_executor_job(_write_file, path, image.content)
        entry["image"] = True
        await self._async_save()

    async def _async_purge_interval(self, _now) -> None:
        await self.async_purge()

    async def async_purge(self) -> None:
        """Alte Bilder und alte Protokolleinträge löschen."""
        now_ms = int(time.time() * 1000)
        image_limit = now_ms - self.retention_days * 86400000
        log_limit = now_ms - LOG_KEEP_DAYS * 86400000

        keep_files: set[str] = set()
        for press in self.presses:
            if press.get("image") and press["ts"] < image_limit:
                press["image"] = False
            if press.get("image"):
                keep_files.add(f"{press['ts']}.jpg")
        self.presses = [p for p in self.presses if p["ts"] >= log_limit]

        await self.hass.async_add_executor_job(
            _delete_other_files, self.folder, keep_files
        )
        await self._async_save()

    async def _async_save(self) -> None:
        self.presses.sort(key=lambda p: p["ts"])
        await self._store.async_save({"presses": self.presses})


def _write_file(path: str, content: bytes) -> None:
    with open(path, "wb") as file:
        file.write(content)
    os.chmod(path, 0o600)


def _delete_other_files(folder: str, keep: set[str]) -> None:
    if not os.path.isdir(folder):
        return
    for name in os.listdir(folder):
        if name not in keep:
            try:
                os.remove(os.path.join(folder, name))
            except OSError as err:
                _LOGGER.warning("Bild %s konnte nicht gelöscht werden: %s", name, err)


def _find(hass: HomeAssistant, entity_id: str) -> DoorbellLog | None:
    for item in hass.data.get(DOMAIN, {}).values():
        if isinstance(item, DoorbellLog) and item.doorbell == entity_id:
            return item
    return None


@websocket_api.websocket_command(
    {
        vol.Required("type"): "lutarym_event_snapshot_recorder/presses",
        vol.Required("entity_id"): cv.entity_id,
    }
)
@callback
def ws_presses(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Protokoll einer Klingel an die Karte liefern."""
    doorbell = _find(hass, msg["entity_id"])
    if doorbell is None:
        connection.send_error(
            msg["id"], "not_found", "Keine Event Snapshot Recorder Einrichtung für diese Entität"
        )
        return
    connection.send_result(
        msg["id"],
        {
            "entry_id": doorbell.entry.entry_id,
            "retention_days": doorbell.retention_days,
            "presses": doorbell.presses,
        },
    )


class DoorbellImageView(HomeAssistantView):
    """Liefert gespeicherte Bilder nur an angemeldete Benutzer."""

    url = IMAGE_URL
    name = "api:lutarym_event_snapshot_recorder:image"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, filename: str) -> web.StreamResponse:
        hass: HomeAssistant = request.app[KEY_HASS]
        if not ENTRY_ID_RE.match(entry_id) or not FILENAME_RE.match(filename):
            return web.Response(status=404)
        doorbell = hass.data.get(DOMAIN, {}).get(entry_id)
        if not isinstance(doorbell, DoorbellLog):
            return web.Response(status=404)
        path = os.path.join(doorbell.folder, filename)
        if not await hass.async_add_executor_job(os.path.isfile, path):
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
