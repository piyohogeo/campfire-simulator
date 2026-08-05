"""Machine-readable execution plan for matched char-depth experiments."""

import csv
import json
from dataclasses import dataclass
from pathlib import Path


DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "data"
PROTOCOL_PATH = DATA_DIRECTORY / "char_depth_experiment_protocol.json"
SCHEDULE_PATH = DATA_DIRECTORY / "char_depth_run_schedule.csv"
EXPECTED_TEMPLATE_FILENAMES = (
    "char_depth_run_schedule.csv",
    "char_depth_event_log_template.csv",
    "char_depth_mass_history_template.csv",
    "char_depth_temperature_history_template.csv",
    "char_depth_surface_history_template.csv",
    "char_depth_measurement_template.csv",
)


@dataclass(frozen=True)
class CharDepthExperimentRun:
    """One independently interrupted cone-calorimeter run."""

    run_id: str
    incident_heat_flux_kw_m2: float
    scheduled_interruption_s: float
    replicate_id: int
    expected_run_directory: str

    @property
    def slot(self) -> tuple[float, float, int]:
        return (
            self.incident_heat_flux_kw_m2,
            self.scheduled_interruption_s,
            self.replicate_id,
        )


@dataclass(frozen=True)
class CharDepthExperimentPlanReadiness:
    """Static completeness and external authorization state of the plan."""

    protocol_id: str
    scheduled_run_count: int
    unique_slot_count: int
    template_file_count: int
    missing_template_files: tuple[str, ...]
    invalid_schedule_rows: tuple[str, ...]
    duplicate_slots: tuple[tuple[float, float, int], ...]
    technical_plan_complete: bool
    authorized_to_execute: bool
    missing_external_approvals: tuple[str, ...]


def expected_run_id(flux_kw_m2: float, time_s: float, replicate_id: int) -> str:
    return (
        f"CF6O-F{int(flux_kw_m2):03d}-T{int(time_s):04d}-"
        f"R{int(replicate_id):02d}"
    )


def load_char_depth_experiment_protocol(path: Path | None = None) -> dict:
    protocol_path = Path(path or PROTOCOL_PATH)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("schema_version") != 1:
        raise ValueError("Unsupported char-depth experiment protocol schema")
    if protocol.get("protocol_id") != "CAMPFIRE_PHASE6O_MATCHED_CHAR_DEPTH_V1":
        raise ValueError("Unexpected char-depth experiment protocol")
    if tuple(protocol.get("required_template_files", ())) != (
        EXPECTED_TEMPLATE_FILENAMES
    ):
        raise ValueError("Experiment protocol template contract changed")
    authorization = protocol.get("external_authorization_gate", {})
    if authorization.get("authorized_to_execute") is not False:
        raise ValueError("Repository protocol must not grant fire-test authorization")
    return protocol


def load_char_depth_run_schedule(
    path: Path | None = None,
) -> tuple[CharDepthExperimentRun, ...]:
    schedule_path = Path(path or SCHEDULE_PATH)
    with schedule_path.open(newline="", encoding="utf-8") as schedule_file:
        reader = csv.DictReader(schedule_file)
        expected_columns = {
            "run_id",
            "incident_heat_flux_kw_m2",
            "scheduled_interruption_s",
            "replicate_id",
            "expected_run_directory",
        }
        if set(reader.fieldnames or ()) != expected_columns:
            raise ValueError("Unexpected char-depth run schedule columns")
        return tuple(
            CharDepthExperimentRun(
                run_id=row["run_id"].strip(),
                incident_heat_flux_kw_m2=float(
                    row["incident_heat_flux_kw_m2"]
                ),
                scheduled_interruption_s=float(
                    row["scheduled_interruption_s"]
                ),
                replicate_id=int(row["replicate_id"]),
                expected_run_directory=row["expected_run_directory"].strip(),
            )
            for row in reader
        )


def evaluate_char_depth_experiment_plan(
    *,
    protocol_path: Path | None = None,
    schedule_path: Path | None = None,
    data_directory: Path | None = None,
) -> CharDepthExperimentPlanReadiness:
    """Validate the issued schedule and templates without authorizing a fire test."""

    protocol = load_char_depth_experiment_protocol(protocol_path)
    runs = load_char_depth_run_schedule(schedule_path)
    root = Path(data_directory or DATA_DIRECTORY)
    missing_templates = tuple(
        filename
        for filename in EXPECTED_TEMPLATE_FILENAMES
        if not (root / filename).is_file()
    )
    invalid_rows = []
    grouped: dict[tuple[float, float, int], list[CharDepthExperimentRun]] = {}
    for run in runs:
        grouped.setdefault(run.slot, []).append(run)
        expected_id = expected_run_id(*run.slot)
        expected_directory = f"runs/{expected_id}"
        if run.run_id != expected_id or run.expected_run_directory != expected_directory:
            invalid_rows.append(run.run_id)
    duplicate_slots = tuple(
        sorted(slot for slot, slot_runs in grouped.items() if len(slot_runs) > 1)
    )
    required_slots = {
        (flux, time_s, replicate_id)
        for flux in (35.0, 70.0)
        for time_s in (60.0, 180.0, 300.0, 600.0)
        for replicate_id in (1, 2, 3)
    }
    technical_complete = (
        set(grouped) == required_slots
        and not missing_templates
        and not invalid_rows
        and not duplicate_slots
        and len(runs) == 24
    )
    authorization = protocol["external_authorization_gate"]
    return CharDepthExperimentPlanReadiness(
        protocol_id=protocol["protocol_id"],
        scheduled_run_count=len(runs),
        unique_slot_count=len(grouped),
        template_file_count=(
            len(EXPECTED_TEMPLATE_FILENAMES) - len(missing_templates)
        ),
        missing_template_files=missing_templates,
        invalid_schedule_rows=tuple(invalid_rows),
        duplicate_slots=duplicate_slots,
        technical_plan_complete=technical_complete,
        authorized_to_execute=bool(authorization["authorized_to_execute"]),
        missing_external_approvals=tuple(authorization["missing_approvals"]),
    )
