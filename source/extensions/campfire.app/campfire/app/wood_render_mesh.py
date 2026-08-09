"""Stable render-only Mesh and atlas mapping for cylindrical wood cells."""

from __future__ import annotations

from dataclasses import dataclass
import math

from pxr import Gf, Sdf, UsdGeom, Vt


WOOD_AXIAL_CELLS = 24
WOOD_CIRCUMFERENTIAL_CELLS = 12
WOOD_RADIAL_CELLS = 4
WOOD_SURFACE_CELLS_PER_LOG = 360
WOOD_RENDER_MAX_LOGS = 20
WOOD_ATLAS_TILE_COLUMNS = 5
WOOD_ATLAS_TILE_ROWS = 4
WOOD_ATLAS_CELL_COLUMNS = 24
WOOD_ATLAS_CELL_ROWS = 15
WOOD_ATLAS_CELL_STRIDE_PX = 1
WOOD_ATLAS_GUTTER_PX = 0
WOOD_ATLAS_WIDTH_PX = (
    WOOD_ATLAS_TILE_COLUMNS * WOOD_ATLAS_CELL_COLUMNS * WOOD_ATLAS_CELL_STRIDE_PX
)
WOOD_ATLAS_HEIGHT_PX = (
    WOOD_ATLAS_TILE_ROWS * WOOD_ATLAS_CELL_ROWS * WOOD_ATLAS_CELL_STRIDE_PX
)


@dataclass(frozen=True)
class WoodRenderMeshData:
    points: tuple
    face_vertex_counts: tuple[int, ...]
    face_vertex_indices: tuple[int, ...]
    face_surface_indices: tuple[int, ...]
    face_varying_surface_indices: tuple[int, ...]
    face_varying_uvs: tuple


@dataclass(frozen=True)
class WoodAtlasDescriptor:
    """Session-stable atlas layout authored before stage connection."""

    render_log_count: int
    tile_columns: int
    tile_rows: int
    cell_stride_px: int = WOOD_ATLAS_CELL_STRIDE_PX

    def __post_init__(self):
        if not 1 <= self.render_log_count <= WOOD_RENDER_MAX_LOGS:
            raise ValueError("Wood atlas requires 1..20 render logs")
        if not 1 <= self.tile_columns <= WOOD_ATLAS_TILE_COLUMNS:
            raise ValueError("Wood atlas tile column count is invalid")
        if self.tile_rows <= 0:
            raise ValueError("Wood atlas tile row count is invalid")
        if self.tile_columns * self.tile_rows < self.render_log_count:
            raise ValueError("Wood atlas does not contain every render log slot")
        if self.cell_stride_px <= 0:
            raise ValueError("Wood atlas cell stride must be positive")

    @property
    def slot_capacity(self) -> int:
        return self.tile_columns * self.tile_rows

    @property
    def width_px(self) -> int:
        return self.tile_columns * WOOD_ATLAS_CELL_COLUMNS * self.cell_stride_px

    @property
    def height_px(self) -> int:
        return self.tile_rows * WOOD_ATLAS_CELL_ROWS * self.cell_stride_px

    @property
    def bytes_per_rgba8_atlas(self) -> int:
        return self.width_px * self.height_px * 4


def compact_atlas_descriptor(
    render_log_count: int, *, cell_stride_px: int = WOOD_ATLAS_CELL_STRIDE_PX
) -> WoodAtlasDescriptor:
    """Return the smallest stable row-major descriptor with at most five columns."""

    render_log_count = int(render_log_count)
    tile_columns = min(WOOD_ATLAS_TILE_COLUMNS, render_log_count)
    tile_rows = int(math.ceil(render_log_count / tile_columns))
    return WoodAtlasDescriptor(
        render_log_count,
        tile_columns,
        tile_rows,
        int(cell_stride_px),
    )


WOOD_ATLAS_MAX_DESCRIPTOR = compact_atlas_descriptor(WOOD_RENDER_MAX_LOGS)


def local_cell_index(axial: int, circumferential: int, radial: int) -> int:
    return (
        axial * WOOD_CIRCUMFERENTIAL_CELLS * WOOD_RADIAL_CELLS
        + circumferential * WOOD_RADIAL_CELLS
        + radial
    )


def surface_cell_ordinal_map() -> dict[int, int]:
    """Mirror the native ascending-local-cell surface packing order."""

    result = {}
    ordinal = 0
    for axial in range(WOOD_AXIAL_CELLS):
        for circumferential in range(WOOD_CIRCUMFERENTIAL_CELLS):
            for radial in range(WOOD_RADIAL_CELLS):
                if axial in (0, WOOD_AXIAL_CELLS - 1) or radial == WOOD_RADIAL_CELLS - 1:
                    result[local_cell_index(axial, circumferential, radial)] = ordinal
                    ordinal += 1
    if ordinal != WOOD_SURFACE_CELLS_PER_LOG:
        raise AssertionError(f"Unexpected wood surface cell count: {ordinal}")
    return result


def atlas_uv(
    log_slot: int,
    local_surface_index: int,
    descriptor: WoodAtlasDescriptor | None = None,
) -> Gf.Vec2f:
    """Return the centre of one immutable surface-state texel."""

    descriptor = WOOD_ATLAS_MAX_DESCRIPTOR if descriptor is None else descriptor
    if not 0 <= log_slot < descriptor.render_log_count:
        raise ValueError("Wood render log slot is outside the atlas descriptor")
    if not 0 <= local_surface_index < WOOD_SURFACE_CELLS_PER_LOG:
        raise ValueError("Wood render surface index is outside 0..359")
    tile_x = log_slot % descriptor.tile_columns
    tile_y = log_slot // descriptor.tile_columns
    cell_x = local_surface_index % WOOD_ATLAS_CELL_COLUMNS
    cell_y = local_surface_index // WOOD_ATLAS_CELL_COLUMNS
    pixel_x = (
        (tile_x * WOOD_ATLAS_CELL_COLUMNS + cell_x) * descriptor.cell_stride_px
        + 0.5 * descriptor.cell_stride_px
    )
    pixel_y = (
        (tile_y * WOOD_ATLAS_CELL_ROWS + cell_y) * descriptor.cell_stride_px
        + 0.5 * descriptor.cell_stride_px
    )
    return Gf.Vec2f(
        pixel_x / descriptor.width_px,
        pixel_y / descriptor.height_px,
    )


def build_wood_render_mesh_data(
    radius_m: float,
    length_m: float,
    log_slot: int,
    descriptor: WoodAtlasDescriptor | None = None,
) -> WoodRenderMeshData:
    """Build fixed topology for 24x12x4 surface state, local X axial."""

    if radius_m <= 0.0 or length_m <= 0.0:
        raise ValueError("Wood render dimensions must be positive")
    descriptor = WOOD_ATLAS_MAX_DESCRIPTOR if descriptor is None else descriptor
    atlas_uv(log_slot, 0, descriptor)
    ordinal_by_cell = surface_cell_ordinal_map()
    points = []
    counts = []
    indices = []
    face_surface_indices = []

    # Side grid. Duplicate the angular seam at column 12 so UV and geometry
    # identity remain explicit while positions coincide exactly.
    for axial_edge in range(WOOD_AXIAL_CELLS + 1):
        x = -0.5 * length_m + length_m * axial_edge / WOOD_AXIAL_CELLS
        for circum_edge in range(WOOD_CIRCUMFERENTIAL_CELLS + 1):
            angle = 2.0 * math.pi * circum_edge / WOOD_CIRCUMFERENTIAL_CELLS
            points.append(Gf.Vec3f(x, radius_m * math.cos(angle), radius_m * math.sin(angle)))
    side_stride = WOOD_CIRCUMFERENTIAL_CELLS + 1
    for axial in range(WOOD_AXIAL_CELLS):
        for circumferential in range(WOOD_CIRCUMFERENTIAL_CELLS):
            lower = axial * side_stride + circumferential
            upper = (axial + 1) * side_stride + circumferential
            counts.append(4)
            indices.extend((lower, upper, upper + 1, lower + 1))
            face_surface_indices.append(
                ordinal_by_cell[
                    local_cell_index(
                        axial, circumferential, WOOD_RADIAL_CELLS - 1
                    )
                ]
            )

    # Each cap has one centre plus four boundary rings. The inner radial cell
    # is a triangle; the other three are annular quads. Outer cap faces reuse
    # the same surface identity as the corresponding side-end faces.
    for axial, x, reverse in (
        (0, -0.5 * length_m, True),
        (WOOD_AXIAL_CELLS - 1, 0.5 * length_m, False),
    ):
        cap_base = len(points)
        points.append(Gf.Vec3f(x, 0.0, 0.0))
        for radial_edge in range(1, WOOD_RADIAL_CELLS + 1):
            radius = radius_m * radial_edge / WOOD_RADIAL_CELLS
            for circum_edge in range(WOOD_CIRCUMFERENTIAL_CELLS + 1):
                angle = 2.0 * math.pi * circum_edge / WOOD_CIRCUMFERENTIAL_CELLS
                points.append(Gf.Vec3f(x, radius * math.cos(angle), radius * math.sin(angle)))
        for radial in range(WOOD_RADIAL_CELLS):
            for circumferential in range(WOOD_CIRCUMFERENTIAL_CELLS):
                if radial == 0:
                    ring = cap_base + 1
                    face = (cap_base, ring + circumferential, ring + circumferential + 1)
                else:
                    inner = cap_base + 1 + (radial - 1) * side_stride
                    outer = cap_base + 1 + radial * side_stride
                    face = (
                        inner + circumferential,
                        outer + circumferential,
                        outer + circumferential + 1,
                        inner + circumferential + 1,
                    )
                if reverse:
                    face = tuple(reversed(face))
                counts.append(len(face))
                indices.extend(face)
                face_surface_indices.append(
                    ordinal_by_cell[
                        local_cell_index(axial, circumferential, radial)
                    ]
                )

    face_varying_surface_indices = tuple(
        surface_index
        for count, surface_index in zip(counts, face_surface_indices)
        for _ in range(count)
    )
    face_varying_uvs = tuple(
        atlas_uv(log_slot, surface_index, descriptor)
        for surface_index in face_varying_surface_indices
    )
    if len(set(face_surface_indices)) != WOOD_SURFACE_CELLS_PER_LOG:
        raise AssertionError("Mesh does not reference all 360 surface identities")
    return WoodRenderMeshData(
        tuple(points),
        tuple(counts),
        tuple(indices),
        tuple(face_surface_indices),
        face_varying_surface_indices,
        face_varying_uvs,
    )


def author_wood_render_mesh(
    mesh: UsdGeom.Mesh,
    radius_m: float,
    length_m: float,
    log_slot: int,
    descriptor: WoodAtlasDescriptor | None = None,
) -> WoodRenderMeshData:
    """Author topology and immutable face-varying lookup primvars once."""

    data = build_wood_render_mesh_data(
        radius_m, length_m, log_slot, descriptor=descriptor
    )
    mesh.CreatePointsAttr(Vt.Vec3fArray(data.points))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray(data.face_vertex_counts))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(data.face_vertex_indices))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(False)
    primvars = UsdGeom.PrimvarsAPI(mesh.GetPrim())
    st = primvars.CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    )
    st.Set(Vt.Vec2fArray(data.face_varying_uvs))
    surface_index = primvars.CreatePrimvar(
        "surfaceIndex", Sdf.ValueTypeNames.IntArray, UsdGeom.Tokens.uniform
    )
    surface_index.Set(Vt.IntArray(data.face_surface_indices))
    return data


def author_wood_render_mesh_uv(
    mesh: UsdGeom.Mesh,
    log_slot: int,
    descriptor: WoodAtlasDescriptor,
) -> tuple:
    """Re-author only immutable lookup UVs before a stage is connected."""

    counts = tuple(int(value) for value in mesh.GetFaceVertexCountsAttr().Get())
    primvars = UsdGeom.PrimvarsAPI(mesh.GetPrim())
    surface_indices = tuple(
        int(value) for value in primvars.GetPrimvar("surfaceIndex").Get()
    )
    if len(counts) != len(surface_indices):
        raise ValueError("Wood render Mesh surface identity is malformed")
    face_varying_uvs = tuple(
        atlas_uv(log_slot, surface_index, descriptor)
        for count, surface_index in zip(counts, surface_indices)
        for _ in range(count)
    )
    primvars.GetPrimvar("st").Set(Vt.Vec2fArray(face_varying_uvs))
    return face_varying_uvs
