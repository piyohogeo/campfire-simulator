"""Record the installed PhysX contact-report API surface without guessing."""

import json
from pathlib import Path

import carb
import omni.kit.app
from omni.physx import get_physx_simulation_interface
from pxr import PhysxSchema


output = Path(carb.settings.get_settings().get_as_string("/phasev3mb/output"))
interface = get_physx_simulation_interface()
payload = {
    "interface_contact_members": sorted(
        name for name in dir(interface) if "contact" in name.lower()
    ),
    "schema_contact_members": sorted(
        name for name in dir(PhysxSchema) if "contact" in name.lower()
    ),
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
omni.kit.app.get_app().post_uncancellable_quit(0)
