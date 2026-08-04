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
from .wood import LogSpec, create_log, get_log_world_position, list_log_ids, move_log

__all__ = [
    "CAMERA_PATH",
    "ASH",
    "CHAR",
    "DEPLETED",
    "DRY_WOOD",
    "FLOW_EMITTER_PATH",
    "FLOW_SIMULATE_PATH",
    "PHASE2_ADDED_LOG_ID",
    "PHASE3_DRY_LOG_ID",
    "PHASE3_WET_LOG_ID",
    "PYROLYZING",
    "WET_WOOD",
    "CampfireAppExtension",
    "FlowSourceState",
    "LogSpec",
    "WoodModelParameters",
    "WoodThermalModel",
    "add_scenario_log",
    "create_log",
    "create_cylindrical_wood_model",
    "create_phase3_models",
    "emitter_position_for_frame",
    "export_stage",
    "populate_fixed_scene",
    "populate_flow_scene",
    "populate_phase2_scene",
    "populate_phase3_scene",
    "get_log_world_position",
    "list_log_ids",
    "load_model_from_prim",
    "move_log",
    "set_emitter_follow",
    "save_model_to_prim",
    "flow_source_from_model",
    "update_flow_source",
]
