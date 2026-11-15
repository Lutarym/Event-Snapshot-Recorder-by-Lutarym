# Event Snapshot Recorder by Lutarym

A Home Assistant integration that logs every doorbell press, takes a camera snapshot on each press and deletes the snapshots after a configurable number of days.

It is the backend for the [Doorbell Camera Card by Lutarym](https://github.com/YOUR_GITHUB_USER/doorbell-camera-card-by-lutarym).

## Features

- Logs every doorbell press (press only, release is ignored)
- Takes a camera snapshot on every press
- Snapshots are deleted automatically after the configured number of days
- Press log is kept for one year, independent of the recorder settings
- Snapshots are stored outside the `www` folder and are only available to logged in users
- Setup and options completely in the UI

## Installation

### HACS (custom repository)

1. Open HACS in Home Assistant.
2. Open the menu (three dots, top right) and choose **Custom repositories**.
3. Add the URL of this repository and select the type **Integration**.
4. Search for **Event Snapshot Recorder by Lutarym** and download it.
5. Restart Home Assistant.

### Manual

1. Copy `custom_components/lutarym_event_snapshot_recorder` to `/config/custom_components/`.
2. Restart Home Assistant.

## Setup

1. Go to **Settings > Devices & services > Add integration**.
2. Search for **Event Snapshot Recorder by Lutarym**.
3. Choose the doorbell entity, the camera entity and how many days snapshots are kept.

Camera and retention can be changed later with **Configure** on the integration.

## Storage

- Snapshots: `/config/lutarym_event_snapshot_recorder/<entry_id>/`
- Press log: `/config/.storage/lutarym_event_snapshot_recorder.<entry_id>`

Removing the integration deletes all snapshots and the press log.

## Notes

- For `binary_sensor` and similar entities, only the change to `on` counts as a press.
- For `event` entities, every new event counts as a press.
- Expired snapshots are deleted every hour and right after the retention is changed.
