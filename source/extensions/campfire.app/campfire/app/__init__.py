# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.

from .extension import CampfireAppExtension
from .calibration import (
    CouponResult,
    build_replicate_split_targets,
    calibration_candidates,
    create_equivalent_coupon,
    evaluate_parameters,
    load_nist_plywood_reference,
    run_nist_plywood_calibration,
    simulate_equivalent_coupon,
    write_calibration_svg,
    write_holdout_svg,
    write_replicate_holdout_svg,
)
from .combustion import (
    ASH,
    CHAR,
    DEPLETED,
    DRY_WOOD,
    PYROLYZING,
    WET_WOOD,
    FlowSourceState,
    WoodModelParameters,
    WoodThermalModel,
    create_cylindrical_wood_model,
    flow_source_from_model,
    load_model_from_prim,
    save_model_to_prim,
)
from .air_supply import (
    AirSupplyResult,
    LogPlacement,
    apply_oxygen_to_model,
    dense_stack_placements,
    estimate_air_supply,
    heat_feedback_factor,
    log_cabin_placements,
    run_stack_air_comparison,
)
from .flow_scene import (
    FLOW_EMITTER_PATH,
    FLOW_SIMULATE_PATH,
    emitter_position_for_frame,
    populate_flow_scene,
)
from .scene import CAMERA_PATH, export_stage, populate_fixed_scene
from .phase2_scene import (
    PHASE2_ADDED_LOG_ID,
    add_scenario_log,
    populate_phase2_scene,
    set_emitter_follow,
)
from .phase3_scene import (
    PHASE3_DRY_LOG_ID,
    PHASE3_WET_LOG_ID,
    create_phase3_models,
    populate_phase3_scene,
    update_flow_source,
)
from .phase4_scene import phase4_placements, populate_phase4_scene
from .phase5_scene import (
    PHASE5_JOINT_PATH,
    PHASE5_SEGMENT_PATHS,
    create_phase5_model,
    populate_phase5_scene,
    release_phase5_structure,
)
from .phase6_scene import (
    PHASE6_BAR_ROOT,
    PHASE6_FLUXES,
    PHASE6_SERIES,
    apply_phase6_calibration,
    populate_phase6_scene,
)
from .support import (
    CrossSectionSupport,
    SegmentPhysicsUpdate,
    SupportAssessment,
    assess_cross_section_support,
    burn_to_support_failure,
    create_collapse_support_model,
    release_segment_joint,
    run_collapse_reignition_scenario,
    segment_mass_kg,
)
from .wood import LogSpec, create_log, get_log_world_position, list_log_ids, move_log

__all__ = [
    "CAMERA_PATH",
    "ASH",
    "AirSupplyResult",
    "CHAR",
    "DEPLETED",
    "DRY_WOOD",
    "FLOW_EMITTER_PATH",
    "FLOW_SIMULATE_PATH",
    "PHASE2_ADDED_LOG_ID",
    "PHASE3_DRY_LOG_ID",
    "PHASE3_WET_LOG_ID",
    "PHASE5_JOINT_PATH",
    "PHASE5_SEGMENT_PATHS",
    "PHASE6_BAR_ROOT",
    "PHASE6_FLUXES",
    "PHASE6_SERIES",
    "PYROLYZING",
    "WET_WOOD",
    "CampfireAppExtension",
    "CouponResult",
    "CrossSectionSupport",
    "FlowSourceState",
    "LogSpec",
    "LogPlacement",
    "SegmentPhysicsUpdate",
    "SupportAssessment",
    "WoodModelParameters",
    "WoodThermalModel",
    "add_scenario_log",
    "apply_phase6_calibration",
    "create_log",
    "create_equivalent_coupon",
    "create_cylindrical_wood_model",
    "create_phase3_models",
    "create_phase5_model",
    "dense_stack_placements",
    "estimate_air_supply",
    "evaluate_parameters",
    "emitter_position_for_frame",
    "export_stage",
    "populate_fixed_scene",
    "populate_flow_scene",
    "populate_phase2_scene",
    "populate_phase3_scene",
    "populate_phase4_scene",
    "populate_phase5_scene",
    "populate_phase6_scene",
    "get_log_world_position",
    "list_log_ids",
    "load_model_from_prim",
    "load_nist_plywood_reference",
    "move_log",
    "set_emitter_follow",
    "save_model_to_prim",
    "flow_source_from_model",
    "heat_feedback_factor",
    "log_cabin_placements",
    "run_stack_air_comparison",
    "run_collapse_reignition_scenario",
    "run_nist_plywood_calibration",
    "phase4_placements",
    "apply_oxygen_to_model",
    "assess_cross_section_support",
    "burn_to_support_failure",
    "build_replicate_split_targets",
    "create_collapse_support_model",
    "release_phase5_structure",
    "release_segment_joint",
    "segment_mass_kg",
    "simulate_equivalent_coupon",
    "calibration_candidates",
    "update_flow_source",
    "write_calibration_svg",
    "write_holdout_svg",
    "write_replicate_holdout_svg",
]
