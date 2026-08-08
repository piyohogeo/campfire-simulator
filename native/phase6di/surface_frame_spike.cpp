#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

#if defined(_WIN32) && defined(CAMPFIRE_SURFACE_FRAME_SPIKE_EXPORTS)
#define CAMPFIRE_FRAME_API extern "C" __declspec(dllexport)
#else
#define CAMPFIRE_FRAME_API extern "C"
#endif

namespace {
constexpr double kFrameTolerance = 1.0e-6;
constexpr double kDeterminantTolerance = 4.0e-6;

double dot3(const double* const first, const double* const second) {
  return first[0] * second[0] + first[1] * second[1] +
         first[2] * second[2];
}

double determinant3(
    const double* const axis_x,
    const double* const axis_y,
    const double* const axis_z) {
  return axis_x[0] *
             (axis_y[1] * axis_z[2] - axis_y[2] * axis_z[1]) -
         axis_x[1] *
             (axis_y[0] * axis_z[2] - axis_y[2] * axis_z[0]) +
         axis_x[2] *
             (axis_y[0] * axis_z[1] - axis_y[1] * axis_z[0]);
}

bool valid_frame(const double* const frame) {
  for (std::size_t component = 0; component < 9; ++component) {
    if (!std::isfinite(frame[component])) {
      return false;
    }
  }
  const double* const axis_x = frame;
  const double* const axis_y = frame + 3;
  const double* const axis_z = frame + 6;
  if (std::abs(dot3(axis_x, axis_x) - 1.0) > kFrameTolerance ||
      std::abs(dot3(axis_y, axis_y) - 1.0) > kFrameTolerance ||
      std::abs(dot3(axis_z, axis_z) - 1.0) > kFrameTolerance ||
      std::abs(dot3(axis_x, axis_y)) > kFrameTolerance ||
      std::abs(dot3(axis_x, axis_z)) > kFrameTolerance ||
      std::abs(dot3(axis_y, axis_z)) > kFrameTolerance) {
    return false;
  }
  const double determinant = determinant3(axis_x, axis_y, axis_z);
  return determinant > 0.0 &&
         std::abs(determinant - 1.0) <= kDeterminantTolerance;
}
}  // namespace

CAMPFIRE_FRAME_API std::int32_t campfire_surface_frame_spike_abi_version() {
  return 1;
}

CAMPFIRE_FRAME_API double campfire_surface_frame_spike_tolerance() {
  return kFrameTolerance;
}

CAMPFIRE_FRAME_API std::int32_t campfire_surface_layout_frames(
    const double* const surface_exposure,
    const std::size_t log_count,
    const std::size_t cells_per_log,
    const std::size_t axial_cells,
    const std::size_t circumferential_cells,
    const std::size_t radial_cells,
    const double radius_m,
    const double length_m,
    const double* const origins_xyz,
    const double* const frames_xyz,
    float* const point_positions_xyz,
    const std::size_t point_capacity,
    std::size_t* const point_count) {
  if (surface_exposure == nullptr || origins_xyz == nullptr ||
      frames_xyz == nullptr || point_positions_xyz == nullptr ||
      point_count == nullptr || log_count == 0 || cells_per_log == 0 ||
      axial_cells == 0 || circumferential_cells == 0 || radial_cells == 0 ||
      !std::isfinite(radius_m) || !std::isfinite(length_m) ||
      radius_m <= 0.0 || length_m <= 0.0) {
    return 1;
  }

  const std::size_t maximum = std::numeric_limits<std::size_t>::max();
  if (axial_cells > maximum / circumferential_cells) {
    return 1;
  }
  const std::size_t axial_circumferential =
      axial_cells * circumferential_cells;
  if (axial_circumferential > maximum / radial_cells ||
      axial_circumferential * radial_cells != cells_per_log ||
      log_count > maximum / cells_per_log) {
    return 1;
  }

  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const double* const origin = origins_xyz + log_index * 3;
    if (!std::isfinite(origin[0]) || !std::isfinite(origin[1]) ||
        !std::isfinite(origin[2]) ||
        !valid_frame(frames_xyz + log_index * 9)) {
      return 3;
    }
  }

  const std::size_t total_cells = log_count * cells_per_log;
  std::size_t required_points = 0;
  for (std::size_t cell = 0; cell < total_cells; ++cell) {
    if (!std::isfinite(surface_exposure[cell])) {
      return 1;
    }
    if (surface_exposure[cell] > 0.0) {
      ++required_points;
    }
  }
  if (required_points > point_capacity) {
    return 2;
  }

  const double axial_step = length_m / static_cast<double>(axial_cells);
  const double radial_step = radius_m / static_cast<double>(radial_cells);
  const double two_pi = 6.283185307179586476925286766559;
  std::size_t output = 0;
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t log_begin = log_index * cells_per_log;
    const double* const origin = origins_xyz + log_index * 3;
    const double* const axis_x = frames_xyz + log_index * 9;
    const double* const axis_y = axis_x + 3;
    const double* const axis_z = axis_y + 3;
    for (std::size_t local = 0; local < cells_per_log; ++local) {
      if (surface_exposure[log_begin + local] <= 0.0) {
        continue;
      }
      const std::size_t radial = local % radial_cells;
      const std::size_t circumferential =
          (local / radial_cells) % circumferential_cells;
      const std::size_t axial =
          local / (radial_cells * circumferential_cells);
      const double axial_position =
          -0.5 * length_m +
          (static_cast<double>(axial) + 0.5) * axial_step;
      const double angle =
          two_pi * (static_cast<double>(circumferential) + 0.5) /
          static_cast<double>(circumferential_cells);
      const double radial_position =
          (static_cast<double>(radial) + 0.5) * radial_step;
      const double cross_a = radial_position * std::cos(angle);
      const double cross_b = radial_position * std::sin(angle);
      for (std::size_t component = 0; component < 3; ++component) {
        point_positions_xyz[output * 3 + component] = static_cast<float>(
            origin[component] + axial_position * axis_x[component] +
            cross_a * axis_y[component] + cross_b * axis_z[component]);
      }
      ++output;
    }
  }
  *point_count = output;
  return 0;
}
