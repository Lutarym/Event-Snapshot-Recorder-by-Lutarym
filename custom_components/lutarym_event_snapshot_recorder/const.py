"""Konstanten für Event Snapshot Recorder by Lutarym."""

DOMAIN = "lutarym_event_snapshot_recorder"

CONF_DOORBELL = "doorbell_entity"
CONF_CAMERA = "camera_entity"
CONF_RETENTION = "retention_days"

DEFAULT_RETENTION = 7
MAX_RETENTION = 365

# Wie lange die Klingelzeiten selbst gespeichert bleiben (Protokoll bis 1 Jahr)
LOG_KEEP_DAYS = 366

STORAGE_VERSION = 1
IMAGE_DIR = "lutarym_event_snapshot_recorder"
INVALID_STATES = ("unavailable", "unknown", "", None)
