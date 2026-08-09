"""Actual Kit extension lifecycle boundary for the isolated Phase V3T-E probe."""

import omni.ext


_instance = None
_last_record = {"startup_called": False, "shutdown_called": False, "close_sequence": []}


def get_instance():
    return _instance


def get_record():
    return dict(_last_record)


def register_transport(transport):
    if _instance is None:
        raise RuntimeError("Phase V3T-E lifecycle extension is not started")
    _instance.register_transport(transport)


class PhaseV3TELifecycleExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        global _instance, _last_record
        self.ext_id = ext_id
        self.transport = None
        self.record = {"startup_called": True, "shutdown_called": False, "close_sequence": []}
        _last_record = dict(self.record)
        _instance = self

    def register_transport(self, transport):
        self.transport = transport

    def on_shutdown(self):
        global _instance, _last_record
        self.record["shutdown_called"] = True
        if self.transport is not None:
            self.transport.close()
            self.record["close_sequence"] = list(self.transport.close_sequence)
            self.transport = None
        _last_record = dict(self.record)
        _instance = None
