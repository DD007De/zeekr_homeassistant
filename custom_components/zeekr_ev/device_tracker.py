"""Device tracker platform for Zeekr EV API Integration."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ZeekrCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the device tracker platform."""
    coordinator: ZeekrCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for vin in coordinator.data:
        entities.append(ZeekrDeviceTracker(coordinator, vin))

    async_add_entities(entities)


class ZeekrDeviceTracker(CoordinatorEntity, TrackerEntity):
    """Zeekr Device Tracker."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ZeekrCoordinator, vin: str) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.vin = vin
        self._attr_name = "Location"
        self._attr_unique_id = f"{vin}_location"
        self._last_lat: float | None = None
        self._last_lon: float | None = None

    @property
    def source_type(self) -> SourceType:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    def _refresh_position(self) -> None:
        """Update the cached position, ignoring unreliable fixes.

        The Zeekr cloud returns an unstable position while the car is parked:
        stale/drifted fixes several km off, or none at all. Read blindly this
        made the tracker jump to far-away places or flap to 'unknown'. Since a
        parked car does not move, we:
          - keep the last known position when a poll has no valid fix;
          - ignore fixes the API itself flags as untrustworthy
            (position.posCanBeTrusted == '0');
          - never overwrite a known position while the car is parked
            (engineStatus 'engine-off') — only update while it is moving.
        The position self-corrects on the next drive.
        """
        data = self.coordinator.data.get(self.vin, {})
        basic = data.get("basicVehicleStatus", {}) or {}
        pos = basic.get("position", {}) or {}

        try:
            lat = float(pos["latitude"]) if pos.get("latitude") else None
            lon = float(pos["longitude"]) if pos.get("longitude") else None
        except (ValueError, TypeError):
            lat = lon = None

        if lat is None or lon is None:
            return  # no valid fix — keep last known position
        if str(pos.get("posCanBeTrusted", "1")).strip() == "0":
            return  # API flags this fix as untrustworthy
        parked = str(basic.get("engineStatus", "")).strip().lower() == "engine-off"
        if parked and self._last_lat is not None:
            return  # parked car does not move — hold last known position

        self._last_lat = lat
        self._last_lon = lon

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        self._refresh_position()
        return self._last_lat

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        self._refresh_position()
        return self._last_lon

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self.vin)},
            "name": f"Zeekr {self.vin}",
            "manufacturer": "Zeekr",
        }
