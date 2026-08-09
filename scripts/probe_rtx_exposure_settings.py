"""List public runtime RTX settings related to exposure and tone mapping."""

import asyncio
import json
from pathlib import Path

import carb
import omni.kit.app


def _walk(value, prefix="/rtx"):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_walk(item, f"{prefix}/{key}"))
    elif any(token in prefix.lower() for token in ("exposure", "histogram", "tone", "whitepoint")):
        rows.append({"path": prefix, "value": value, "type": type(value).__name__})
    return rows


async def _run():
    settings = carb.settings.get_settings()
    output = Path(settings.get_as_string("/phasev3tf/exposureOutput")).resolve()
    await omni.kit.app.get_app().next_update_async()
    dictionary = settings.get_settings_dictionary("/rtx")
    payload = dictionary.get_dict() if dictionary is not None else {}
    roots = {}
    for root in (
        "/rtx/post/tonemap",
        "/rtx/post/histogram",
        "/rtx/post/autoExposure",
        "/rtx/post",
    ):
        item = settings.get_settings_dictionary(root)
        roots[root] = item.get_dict() if item is not None else {}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"schema": "campfire.rtx.exposure_settings.v1", "settings": _walk(payload), "roots": roots}, indent=2) + "\n",
        encoding="utf-8",
    )
    omni.kit.app.get_app().post_uncancellable_quit(0)


asyncio.ensure_future(_run())
