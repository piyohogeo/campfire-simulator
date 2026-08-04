"""Small Phase 2 UI that delegates to the same services as headless tests."""

import omni.timeline
import omni.ui as ui
import omni.usd

from .phase2_scene import (
    PHASE2_ADDED_LOG_ID,
    PHASE2_SPAWN_POSITION_M,
    add_scenario_log,
    populate_phase2_scene,
    set_emitter_follow,
)
from .wood import list_log_ids, move_log


class CampfireControlWindow:
    """Minimal controls for add, grab-like reposition and reset operations."""

    def __init__(self):
        self._window = ui.Window("Campfire Controls", width=330, height=230)
        with self._window.frame:
            with ui.VStack(spacing=8, height=0):
                ui.Label("Phase 2 · Dynamic Log MVP", height=28)
                ui.Button("Add falling log", clicked_fn=self._add_log, height=36)
                ui.Button("Lift added log", clicked_fn=self._lift_log, height=36)
                ui.Button("Reset Phase 2 scene", clicked_fn=self._reset, height=36)
                self._status = ui.Label("Ready", word_wrap=True, height=40)

    def destroy(self):
        self._window = None
        self._status = None

    def _stage(self):
        return omni.usd.get_context().get_stage()

    def _pause(self):
        omni.timeline.get_timeline_interface().pause()

    def _add_log(self):
        self._pause()
        stage = self._stage()
        if PHASE2_ADDED_LOG_ID in list_log_ids(stage):
            self._status.text = "Log_04 already exists. Use Lift or Reset."
            return
        add_scenario_log(stage)
        set_emitter_follow(stage, PHASE2_ADDED_LOG_ID)
        self._status.text = "Added Log_04 at 2.60 m. Press Play to drop it."

    def _lift_log(self):
        self._pause()
        stage = self._stage()
        if PHASE2_ADDED_LOG_ID not in list_log_ids(stage):
            add_scenario_log(stage)
        move_log(stage, PHASE2_ADDED_LOG_ID, PHASE2_SPAWN_POSITION_M, 25.0)
        set_emitter_follow(stage, PHASE2_ADDED_LOG_ID)
        self._status.text = "Lifted Log_04. Press Play to release it."

    def _reset(self):
        self._pause()
        populate_phase2_scene(self._stage())
        self._status.text = "Phase 2 scene reset to four logs."
