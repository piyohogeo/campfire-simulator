"""Machine-readable readiness gate for matched plywood char-depth measurements."""

import csv
import math
from dataclasses import dataclass
from pathlib import Path


MEASUREMENT_FIELDS = (
    "initial_thickness_m",
    "current_total_thickness_m",
    "exposed_surface_displacement_m",
    "optical_char_layer_thickness_m",
    "isotherm_300c_layer_thickness_m",
    "thickness_uncertainty_m",
    "char_front_uncertainty_m",
)
SPECIMEN_IDENTITY_FIELDS = (
    "wood_species_by_ply",
    "adhesive_type",
    "individual_ply_thickness_m",
    "oven_dry_density_kg_m3",
    "moisture_ratio_dry_basis",
    "grain_orientation_by_ply_deg",
    "mass_history_file",
)
NUMERIC_SPECIMEN_IDENTITY_FIELDS = (
    "oven_dry_density_kg_m3",
    "moisture_ratio_dry_basis",
)
TEXT_SPECIMEN_IDENTITY_FIELDS = tuple(
    field
    for field in SPECIMEN_IDENTITY_FIELDS
    if field not in NUMERIC_SPECIMEN_IDENTITY_FIELDS
)


@dataclass(frozen=True)
class CharDepthMeasurementObservation:
    """One interrupted-test observation, expressed entirely in SI units."""

    incident_heat_flux_kw_m2: float
    time_s: float
    replicate_id: int
    initial_thickness_m: float | None = None
    current_total_thickness_m: float | None = None
    exposed_surface_displacement_m: float | None = None
    optical_char_layer_thickness_m: float | None = None
    isotherm_300c_layer_thickness_m: float | None = None
    thickness_uncertainty_m: float | None = None
    char_front_uncertainty_m: float | None = None
    wood_species_by_ply: str = ""
    adhesive_type: str = ""
    individual_ply_thickness_m: str = ""
    oven_dry_density_kg_m3: float | None = None
    moisture_ratio_dry_basis: float | None = None
    grain_orientation_by_ply_deg: str = ""
    mass_history_file: str = ""
    notes: str = ""

    @property
    def slot(self) -> tuple[float, float, int]:
        return (
            self.incident_heat_flux_kw_m2,
            self.time_s,
            self.replicate_id,
        )

    @property
    def measurements_complete(self) -> bool:
        return (
            all(getattr(self, field) is not None for field in MEASUREMENT_FIELDS)
            and all(
                getattr(self, field) is not None
                for field in NUMERIC_SPECIMEN_IDENTITY_FIELDS
            )
            and all(
                bool(str(getattr(self, field)).strip())
                for field in TEXT_SPECIMEN_IDENTITY_FIELDS
            )
        )


@dataclass(frozen=True)
class CharDepthMeasurementReadiness:
    """Completeness and validity of the matched observation matrix."""

    required_observation_count: int
    scheduled_observation_count: int
    complete_observation_count: int
    missing_slots: tuple[tuple[float, float, int], ...]
    incomplete_slots: tuple[tuple[float, float, int], ...]
    invalid_slots: tuple[tuple[float, float, int], ...]
    duplicate_slots: tuple[tuple[float, float, int], ...]
    unexpected_slots: tuple[tuple[float, float, int], ...]
    ready_for_physical_char_thickness_calibration: bool


def _optional_float(value: str) -> float | None:
    stripped = value.strip()
    return float(stripped) if stripped else None


def load_char_depth_measurement_csv(
    path: Path,
) -> tuple[CharDepthMeasurementObservation, ...]:
    """Load a scheduled or completed measurement matrix from CSV."""

    observations = []
    with Path(path).open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        expected_fields = {
            "incident_heat_flux_kw_m2",
            "time_s",
            "replicate_id",
            *MEASUREMENT_FIELDS,
            *SPECIMEN_IDENTITY_FIELDS,
            "notes",
        }
        if set(reader.fieldnames or ()) != expected_fields:
            raise ValueError("Unexpected char-depth measurement CSV columns")
        for row in reader:
            observations.append(
                CharDepthMeasurementObservation(
                    incident_heat_flux_kw_m2=float(
                        row["incident_heat_flux_kw_m2"]
                    ),
                    time_s=float(row["time_s"]),
                    replicate_id=int(row["replicate_id"]),
                    initial_thickness_m=_optional_float(row["initial_thickness_m"]),
                    current_total_thickness_m=_optional_float(
                        row["current_total_thickness_m"]
                    ),
                    exposed_surface_displacement_m=_optional_float(
                        row["exposed_surface_displacement_m"]
                    ),
                    optical_char_layer_thickness_m=_optional_float(
                        row["optical_char_layer_thickness_m"]
                    ),
                    isotherm_300c_layer_thickness_m=_optional_float(
                        row["isotherm_300c_layer_thickness_m"]
                    ),
                    thickness_uncertainty_m=_optional_float(
                        row["thickness_uncertainty_m"]
                    ),
                    char_front_uncertainty_m=_optional_float(
                        row["char_front_uncertainty_m"]
                    ),
                    wood_species_by_ply=row["wood_species_by_ply"].strip(),
                    adhesive_type=row["adhesive_type"].strip(),
                    individual_ply_thickness_m=row[
                        "individual_ply_thickness_m"
                    ].strip(),
                    oven_dry_density_kg_m3=_optional_float(
                        row["oven_dry_density_kg_m3"]
                    ),
                    moisture_ratio_dry_basis=_optional_float(
                        row["moisture_ratio_dry_basis"]
                    ),
                    grain_orientation_by_ply_deg=row[
                        "grain_orientation_by_ply_deg"
                    ].strip(),
                    mass_history_file=row["mass_history_file"].strip(),
                    notes=row["notes"].strip(),
                )
            )
    return tuple(observations)


def _observation_is_valid(observation: CharDepthMeasurementObservation) -> bool:
    if not observation.measurements_complete:
        return False
    values = [float(getattr(observation, field)) for field in MEASUREMENT_FIELDS]
    if not all(math.isfinite(value) for value in values):
        return False
    (
        initial_thickness_m,
        current_total_thickness_m,
        _surface_displacement_m,
        optical_depth_m,
        isotherm_depth_m,
        thickness_uncertainty_m,
        front_uncertainty_m,
    ) = values
    try:
        ply_thicknesses_m = tuple(
            float(value)
            for value in observation.individual_ply_thickness_m.split(";")
        )
        grain_orientations_deg = tuple(
            float(value)
            for value in observation.grain_orientation_by_ply_deg.split(";")
        )
    except ValueError:
        return False
    return (
        initial_thickness_m > 0.0
        and current_total_thickness_m > 0.0
        and 0.0 <= optical_depth_m <= current_total_thickness_m
        and 0.0 <= isotherm_depth_m <= current_total_thickness_m
        and thickness_uncertainty_m > 0.0
        and front_uncertainty_m > 0.0
        and len(observation.wood_species_by_ply.split(";")) == 5
        and all(
            species.strip()
            for species in observation.wood_species_by_ply.split(";")
        )
        and len(ply_thicknesses_m) == 5
        and all(
            math.isfinite(thickness_m) and thickness_m > 0.0
            for thickness_m in ply_thicknesses_m
        )
        and math.isclose(
            sum(ply_thicknesses_m), initial_thickness_m, rel_tol=0.02
        )
        and math.isfinite(float(observation.oven_dry_density_kg_m3))
        and float(observation.oven_dry_density_kg_m3) > 0.0
        and math.isfinite(float(observation.moisture_ratio_dry_basis))
        and float(observation.moisture_ratio_dry_basis) >= 0.0
        and len(grain_orientations_deg) == 5
        and all(math.isfinite(angle) for angle in grain_orientations_deg)
    )


def evaluate_char_depth_measurement_readiness(
    observations: tuple[CharDepthMeasurementObservation, ...],
    *,
    required_heat_fluxes_kw_m2: tuple[float, ...],
    required_times_s: tuple[float, ...],
    required_replicate_ids: tuple[int, ...],
) -> CharDepthMeasurementReadiness:
    """Require every planned slot and every physical measurement before opening."""

    required_slots = {
        (float(flux), float(time_s), int(replicate_id))
        for flux in required_heat_fluxes_kw_m2
        for time_s in required_times_s
        for replicate_id in required_replicate_ids
    }
    grouped: dict[
        tuple[float, float, int], list[CharDepthMeasurementObservation]
    ] = {}
    for observation in observations:
        grouped.setdefault(observation.slot, []).append(observation)
    supplied_slots = set(grouped)
    duplicate_slots = tuple(
        sorted(slot for slot, rows in grouped.items() if len(rows) > 1)
    )
    unexpected_slots = tuple(sorted(supplied_slots - required_slots))
    missing_slots = tuple(sorted(required_slots - supplied_slots))
    incomplete_slots = tuple(
        sorted(
            slot
            for slot in required_slots & supplied_slots
            if not grouped[slot][0].measurements_complete
        )
    )
    invalid_slots = tuple(
        sorted(
            slot
            for slot in required_slots & supplied_slots
            if grouped[slot][0].measurements_complete
            and not _observation_is_valid(grouped[slot][0])
        )
    )
    complete_count = sum(
        1
        for slot in required_slots & supplied_slots
        if len(grouped[slot]) == 1 and _observation_is_valid(grouped[slot][0])
    )
    ready = not (
        missing_slots
        or incomplete_slots
        or invalid_slots
        or duplicate_slots
        or unexpected_slots
    )
    return CharDepthMeasurementReadiness(
        required_observation_count=len(required_slots),
        scheduled_observation_count=len(required_slots & supplied_slots),
        complete_observation_count=complete_count,
        missing_slots=missing_slots,
        incomplete_slots=incomplete_slots,
        invalid_slots=invalid_slots,
        duplicate_slots=duplicate_slots,
        unexpected_slots=unexpected_slots,
        ready_for_physical_char_thickness_calibration=ready,
    )
