"""Runtime introspection of fixed Kit dynamic-texture surfaces."""
import json
from pathlib import Path

import carb
import omni.kit.app
import omni.ui as ui
from omni.gpu_foundation_factory import TextureFormat

settings = carb.settings.get_settings()
output = Path(settings.get_as_string("/phasev3/output")).resolve()
report = {"schema": "campfire.phasev3.texture_api_introspection.v1"}
try:
    provider_type = getattr(ui, "DynamicTextureProvider", None)
    report["dynamic_texture_provider_available"] = provider_type is not None
    report["provider_doc"] = getattr(provider_type, "__doc__", None)
    report["provider_methods"] = sorted(
        name for name in dir(provider_type) if not name.startswith("__")
    ) if provider_type else []
    if provider_type:
        provider = provider_type("campfire_phasev3_probe")
        report["instance_attributes"] = {
            name: repr(getattr(provider, name))
            for name in report["provider_methods"]
            if name in ("texture_id", "texture_url", "url", "name")
        }
        report["set_bytes_data_doc"] = getattr(provider.set_bytes_data, "__doc__", None)
        report["set_raw_bytes_data_doc"] = getattr(provider.set_raw_bytes_data, "__doc__", None)
        report["set_bytes_data_from_gpu_available"] = hasattr(provider, "set_bytes_data_from_gpu")
        report["set_bytes_data_from_gpu_doc"] = getattr(
            getattr(provider, "set_bytes_data_from_gpu", None), "__doc__", None
        )
    report["texture_formats"] = {
        name: int(value.value) for name, value in TextureFormat.__members__.items()
        if "RGBA" in name or "16" in name
    }
    report["status"] = "ok"
    exit_code = 0
except Exception as error:
    report.update(status="error", error=f"{type(error).__name__}: {error}")
    exit_code = 1
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
omni.kit.app.get_app().post_uncancellable_quit(exit_code)
