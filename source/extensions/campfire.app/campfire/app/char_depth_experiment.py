"""Machine-readable execution plan for matched char-depth experiments."""

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "data"
PROTOCOL_PATH = DATA_DIRECTORY / "char_depth_experiment_protocol.json"
SCHEDULE_PATH = DATA_DIRECTORY / "char_depth_run_schedule.csv"
LAB_HANDOFF_TEMPLATE_PATH = DATA_DIRECTORY / "char_depth_lab_handoff_template.json"
EXPECTED_TEMPLATE_FILENAMES = (
    "char_depth_run_schedule.csv",
    "char_depth_event_log_template.csv",
    "char_depth_mass_history_template.csv",
    "char_depth_temperature_history_template.csv",
    "char_depth_surface_history_template.csv",
    "char_depth_measurement_template.csv",
)
RUN_CSV_TEMPLATES = {
    "events.csv": "char_depth_event_log_template.csv",
    "mass_history.csv": "char_depth_mass_history_template.csv",
    "temperature_history.csv": "char_depth_temperature_history_template.csv",
    "surface_history.csv": "char_depth_surface_history_template.csv",
}
RUNTIME_HANDOFF_FIELDS = (
    "operator_id",
    "apparatus_id",
    "heat_flux_calibration_record",
    "actual_heat_flux_kw_m2",
    "camera_clock_offset_s",
    "thermocouple_configuration",
    "quench_method_approval",
    "laboratory_safety_sop_approval",
    "apparatus_owner_approval",
)
EXTERNAL_EVIDENCE_FIELDS = (
    "record_reference",
    "responsible_organization",
    "approved_by",
    "approved_at_utc",
)
LAB_REVIEW_FIELDS = (
    "laboratory_name",
    "handoff_prepared_by",
    "handoff_reviewed_by",
    "reviewed_at_utc",
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


@dataclass(frozen=True)
class CharDepthDryRunPackageReadiness:
    """Structural status of a deliberately measurement-free run package."""

    run_id: str
    missing_files: tuple[str, ...]
    missing_directories: tuple[str, ...]
    invalid_files: tuple[str, ...]
    missing_runtime_metadata: tuple[str, ...]
    structural_complete: bool
    contains_measurements: bool
    dry_run_package_complete: bool
    authorized_to_execute: bool
    eligible_for_measurement_import: bool


@dataclass(frozen=True)
class CharDepthLabHandoffReadiness:
    """Completeness of external metadata without repository authorization."""

    protocol_id: str
    run_id: str
    required_runtime_field_count: int
    populated_runtime_field_count: int
    missing_runtime_metadata: tuple[str, ...]
    required_external_evidence_count: int
    populated_external_evidence_count: int
    missing_external_evidence: tuple[str, ...]
    missing_laboratory_review: tuple[str, ...]
    invalid_fields: tuple[str, ...]
    template_contract_complete: bool
    ready_for_external_authorization_review: bool
    repository_can_authorize: bool
    authorized_to_execute: bool


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


def load_char_depth_lab_handoff(path: Path | None = None) -> dict:
    """Load the external handoff form without interpreting it as approval."""

    handoff_path = Path(path or LAB_HANDOFF_TEMPLATE_PATH)
    return json.loads(handoff_path.read_text(encoding="utf-8"))


def _is_supplied(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _is_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.utcoffset() == timedelta(0)


def evaluate_char_depth_lab_handoff(
    path: Path | None = None,
) -> CharDepthLabHandoffReadiness:
    """Validate external-input slots while keeping execution authority external."""

    handoff = load_char_depth_lab_handoff(path)
    protocol = load_char_depth_experiment_protocol()
    invalid_fields = []
    run_id = str(handoff.get("run_id", ""))
    try:
        _scheduled_run(run_id)
    except ValueError:
        invalid_fields.append("run_id")
    if handoff.get("schema_version") != 1:
        invalid_fields.append("schema_version")
    if handoff.get("protocol_id") != protocol["protocol_id"]:
        invalid_fields.append("protocol_id")
    if handoff.get("status") != "awaiting_responsible_laboratory_input":
        invalid_fields.append("status")
    if handoff.get("repository_can_authorize") is not False:
        invalid_fields.append("repository_can_authorize")
    if not isinstance(handoff.get("policy"), str) or not handoff["policy"].strip():
        invalid_fields.append("policy")

    runtime = handoff.get("runtime_metadata", {})
    if not isinstance(runtime, dict) or set(runtime) != set(RUNTIME_HANDOFF_FIELDS):
        invalid_fields.append("runtime_metadata")
        runtime = runtime if isinstance(runtime, dict) else {}
    missing_runtime = tuple(
        field for field in RUNTIME_HANDOFF_FIELDS if not _is_supplied(runtime.get(field))
    )
    for field in (
        set(RUNTIME_HANDOFF_FIELDS)
        - {"actual_heat_flux_kw_m2", "camera_clock_offset_s"}
    ):
        value = runtime.get(field)
        if _is_supplied(value) and (
            not isinstance(value, str) or not value.strip()
        ):
            invalid_fields.append(f"runtime_metadata.{field}")
    actual_flux = runtime.get("actual_heat_flux_kw_m2")
    if _is_supplied(actual_flux):
        try:
            numeric_flux = float(actual_flux)
            if not math.isfinite(numeric_flux) or numeric_flux <= 0.0:
                raise ValueError
        except (TypeError, ValueError):
            invalid_fields.append("runtime_metadata.actual_heat_flux_kw_m2")
    camera_offset = runtime.get("camera_clock_offset_s")
    if _is_supplied(camera_offset):
        try:
            if not math.isfinite(float(camera_offset)):
                raise ValueError
        except (TypeError, ValueError):
            invalid_fields.append("runtime_metadata.camera_clock_offset_s")

    required_evidence = tuple(
        protocol["external_authorization_gate"]["missing_approvals"]
    )
    evidence = handoff.get("external_evidence", {})
    if not isinstance(evidence, dict) or set(evidence) != set(required_evidence):
        invalid_fields.append("external_evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
    missing_evidence = []
    for approval_name in required_evidence:
        record = evidence.get(approval_name, {})
        if not isinstance(record, dict) or set(record) != set(EXTERNAL_EVIDENCE_FIELDS):
            invalid_fields.append(f"external_evidence.{approval_name}")
            missing_evidence.append(approval_name)
            continue
        if not all(_is_supplied(record.get(field)) for field in EXTERNAL_EVIDENCE_FIELDS):
            missing_evidence.append(approval_name)
        for field in EXTERNAL_EVIDENCE_FIELDS:
            value = record.get(field)
            if _is_supplied(value) and (
                not isinstance(value, str) or not value.strip()
            ):
                invalid_fields.append(f"external_evidence.{approval_name}.{field}")
        approved_at = record.get("approved_at_utc")
        if _is_supplied(approved_at) and not _is_utc_timestamp(approved_at):
            invalid_fields.append(
                f"external_evidence.{approval_name}.approved_at_utc"
            )

    review = handoff.get("responsible_laboratory_review", {})
    if not isinstance(review, dict) or set(review) != set(LAB_REVIEW_FIELDS):
        invalid_fields.append("responsible_laboratory_review")
        review = review if isinstance(review, dict) else {}
    missing_review = tuple(
        field for field in LAB_REVIEW_FIELDS if not _is_supplied(review.get(field))
    )
    for field in LAB_REVIEW_FIELDS:
        value = review.get(field)
        if _is_supplied(value) and (
            not isinstance(value, str) or not value.strip()
        ):
            invalid_fields.append(f"responsible_laboratory_review.{field}")
    reviewed_at = review.get("reviewed_at_utc")
    if _is_supplied(reviewed_at) and not _is_utc_timestamp(reviewed_at):
        invalid_fields.append("responsible_laboratory_review.reviewed_at_utc")
    invalid = tuple(sorted(set(invalid_fields)))
    contract_complete = not invalid
    ready_for_review = (
        contract_complete
        and not missing_runtime
        and not missing_evidence
        and not missing_review
    )
    return CharDepthLabHandoffReadiness(
        protocol_id=str(handoff.get("protocol_id", "")),
        run_id=run_id,
        required_runtime_field_count=len(RUNTIME_HANDOFF_FIELDS),
        populated_runtime_field_count=len(RUNTIME_HANDOFF_FIELDS) - len(missing_runtime),
        missing_runtime_metadata=missing_runtime,
        required_external_evidence_count=len(required_evidence),
        populated_external_evidence_count=len(required_evidence) - len(missing_evidence),
        missing_external_evidence=tuple(missing_evidence),
        missing_laboratory_review=missing_review,
        invalid_fields=invalid,
        template_contract_complete=contract_complete,
        ready_for_external_authorization_review=ready_for_review,
        repository_can_authorize=False,
        authorized_to_execute=False,
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


def _scheduled_run(run_id: str) -> CharDepthExperimentRun:
    matches = tuple(
        run for run in load_char_depth_run_schedule() if run.run_id == run_id
    )
    if len(matches) != 1:
        raise ValueError(f"Run ID is not unique in the issued schedule: {run_id}")
    return matches[0]


def create_char_depth_dry_run_package(
    run_id: str, destination_root: Path
) -> Path:
    """Create a blank run package without measurements or execution authority."""

    run = _scheduled_run(run_id)
    protocol = load_char_depth_experiment_protocol()
    root = Path(destination_root).resolve()
    run_directory = root / "runs" / run.run_id
    if run_directory.exists():
        existing = evaluate_char_depth_dry_run_package(run_directory)
        if existing.dry_run_package_complete:
            return run_directory
        raise FileExistsError(
            f"Refusing to overwrite an incomplete or changed run package: {run_directory}"
        )
    run_directory.mkdir(parents=True)
    for directory_name in protocol["run_directory_contract"][
        "required_directories"
    ]:
        (run_directory / directory_name).mkdir()

    manifest = {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "run_id": run.run_id,
        "status": "offline_dry_run_awaiting_instrument_export",
        "dry_run": True,
        "contains_measurements": False,
        "incident_heat_flux_kw_m2": run.incident_heat_flux_kw_m2,
        "scheduled_interruption_s": run.scheduled_interruption_s,
        "replicate_id": run.replicate_id,
        "coordinate_frame": protocol["coordinate_frame"],
        "master_clock": protocol["timebase"]["master_clock"],
        "operator_id": None,
        "apparatus_id": None,
        "heat_flux_calibration_record": None,
        "actual_heat_flux_kw_m2": None,
        "camera_clock_offset_s": None,
        "thermocouple_configuration": None,
        "quench_method_approval": None,
        "laboratory_safety_sop_approval": None,
        "apparatus_owner_approval": None,
    }
    (run_directory / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for target_filename, template_filename in RUN_CSV_TEMPLATES.items():
        (run_directory / target_filename).write_text(
            (DATA_DIRECTORY / template_filename).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    section_measurement = {
        "schema_version": 1,
        "run_id": run.run_id,
        "status": "awaiting_section_measurement",
        "section_plane": None,
        "section_image_file": None,
        "scale_calibration_file": None,
        "operator_id": None,
        "saw_kerf_m": None,
        "material_loss_m": None,
        "elapsed_since_exposure_end_s": None,
        "optical_char_layer_thickness_m": None,
        "optical_trace_file": None,
        "measurement_uncertainty_m": None,
    }
    (run_directory / "section_measurement.json").write_text(
        json.dumps(section_measurement, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return run_directory


def evaluate_char_depth_dry_run_package(
    run_directory: Path,
) -> CharDepthDryRunPackageReadiness:
    """Verify a blank package while refusing to treat it as measured data."""

    path = Path(run_directory).resolve()
    protocol = load_char_depth_experiment_protocol()
    required_files = tuple(
        protocol["run_directory_contract"]["required_files"]
    )
    required_directories = tuple(
        protocol["run_directory_contract"]["required_directories"]
    )
    missing_files = tuple(
        filename for filename in required_files if not (path / filename).is_file()
    )
    missing_directories = tuple(
        name for name in required_directories if not (path / name).is_dir()
    )
    invalid_files = []
    expected_entries = set(required_files) | set(required_directories)
    if path.is_dir():
        invalid_files.extend(
            f"unexpected:{entry.name}"
            for entry in path.iterdir()
            if entry.name not in expected_entries
        )
    manifest = {}
    manifest_path = path / "run_manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            run = _scheduled_run(str(manifest.get("run_id", "")))
            if (
                manifest.get("schema_version") != 1
                or manifest.get("protocol_id") != protocol["protocol_id"]
                or float(manifest.get("incident_heat_flux_kw_m2", -1.0))
                != run.incident_heat_flux_kw_m2
                or float(manifest.get("scheduled_interruption_s", -1.0))
                != run.scheduled_interruption_s
                or int(manifest.get("replicate_id", -1)) != run.replicate_id
                or run.run_id != path.name
                or manifest.get("status")
                != "offline_dry_run_awaiting_instrument_export"
                or manifest.get("coordinate_frame")
                != protocol["coordinate_frame"]
                or manifest.get("master_clock")
                != protocol["timebase"]["master_clock"]
            ):
                invalid_files.append("run_manifest.json")
        except (ValueError, TypeError, json.JSONDecodeError):
            invalid_files.append("run_manifest.json")

    csv_row_counts = {}
    for target_filename, template_filename in RUN_CSV_TEMPLATES.items():
        target_path = path / target_filename
        if not target_path.is_file():
            continue
        with target_path.open(newline="", encoding="utf-8") as target_file:
            target_rows = list(csv.reader(target_file))
        with (DATA_DIRECTORY / template_filename).open(
            newline="", encoding="utf-8"
        ) as template_file:
            template_header = next(csv.reader(template_file))
        if not target_rows or target_rows[0] != template_header:
            invalid_files.append(target_filename)
            csv_row_counts[target_filename] = 0
        else:
            csv_row_counts[target_filename] = len(target_rows) - 1

    section_contains_measurement = False
    section_path = path / "section_measurement.json"
    if section_path.is_file():
        try:
            section = json.loads(section_path.read_text(encoding="utf-8"))
            if (
                section.get("schema_version") != 1
                or section.get("run_id") != manifest.get("run_id")
            ):
                invalid_files.append("section_measurement.json")
            section_contains_measurement = any(
                value is not None
                for field, value in section.items()
                if field not in {"schema_version", "run_id", "status"}
            )
        except json.JSONDecodeError:
            invalid_files.append("section_measurement.json")

    runtime_fields = (
        "operator_id",
        "apparatus_id",
        "heat_flux_calibration_record",
        "actual_heat_flux_kw_m2",
        "camera_clock_offset_s",
        "thermocouple_configuration",
        "quench_method_approval",
        "laboratory_safety_sop_approval",
        "apparatus_owner_approval",
    )
    missing_runtime_metadata = tuple(
        field for field in runtime_fields if manifest.get(field) is None
    )
    evidence_directories_contain_data = any(
        any((path / name).iterdir())
        for name in required_directories
        if (path / name).is_dir()
    )
    contains_measurements = (
        section_contains_measurement
        or evidence_directories_contain_data
        or any(row_count > 0 for row_count in csv_row_counts.values())
    )
    structural_complete = not (
        missing_files or missing_directories or invalid_files
    )
    authorized = bool(
        protocol["external_authorization_gate"]["authorized_to_execute"]
    )
    is_blank_dry_run = (
        manifest.get("dry_run") is True
        and manifest.get("contains_measurements") is False
        and not contains_measurements
        and len(missing_runtime_metadata) == len(runtime_fields)
    )
    return CharDepthDryRunPackageReadiness(
        run_id=str(manifest.get("run_id", path.name)),
        missing_files=missing_files,
        missing_directories=missing_directories,
        invalid_files=tuple(sorted(set(invalid_files))),
        missing_runtime_metadata=missing_runtime_metadata,
        structural_complete=structural_complete,
        contains_measurements=contains_measurements,
        dry_run_package_complete=(
            structural_complete and is_blank_dry_run and not authorized
        ),
        authorized_to_execute=authorized,
        eligible_for_measurement_import=(
            structural_complete
            and contains_measurements
            and not bool(manifest.get("dry_run"))
            and authorized
        ),
    )
