CAMPFIRE_API std::int32_t campfire_native_surface_layout(
    const double* const surface_exposure,
    const std::size_t log_count,
    const std::size_t cells_per_log,
    const std::size_t axial_cells,
    const std::size_t circumferential_cells,
    const std::size_t radial_cells,
    const double radius_m,
    const double length_m,
    const double* const origins_xyz,
    const std::uint32_t* const axial_along_y,
    float* const point_positions_xyz,
    const std::size_t point_capacity,
    std::size_t* const point_count) {
  if (surface_exposure == nullptr || origins_xyz == nullptr ||
      axial_along_y == nullptr || point_positions_xyz == nullptr ||
      point_count == nullptr || log_count == 0 || cells_per_log == 0 ||
      axial_cells == 0 || circumferential_cells == 0 || radial_cells == 0 ||
      axial_cells * circumferential_cells * radial_cells != cells_per_log ||
      radius_m <= 0.0 || length_m <= 0.0) {
    return 1;
  }

  const double dz = length_m / static_cast<double>(axial_cells);
  const double dr = radius_m / static_cast<double>(radial_cells);
  const double two_pi = 6.283185307179586476925286766559;
  std::size_t output = 0;
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t log_begin = log_index * cells_per_log;
    const double origin_x = origins_xyz[log_index * 3];
    const double origin_y = origins_xyz[log_index * 3 + 1];
    const double origin_z = origins_xyz[log_index * 3 + 2];
    for (std::size_t local = 0; local < cells_per_log; ++local) {
      if (surface_exposure[log_begin + local] <= 0.0) {
        continue;
      }
      if (output >= point_capacity) {
        return 2;
      }
      const std::size_t radial = local % radial_cells;
      const std::size_t circumferential =
          (local / radial_cells) % circumferential_cells;
      const std::size_t axial =
          local / (radial_cells * circumferential_cells);
      const double axial_position =
          -0.5 * length_m + (static_cast<double>(axial) + 0.5) * dz;
      const double angle =
          two_pi * (static_cast<double>(circumferential) + 0.5) /
          static_cast<double>(circumferential_cells);
      const double radial_position =
          (static_cast<double>(radial) + 0.5) * dr;
      const double cross_a = radial_position * std::cos(angle);
      const double cross_b = radial_position * std::sin(angle);
      const bool rotate = axial_along_y[log_index] != 0;
      point_positions_xyz[output * 3] = static_cast<float>(
          rotate ? origin_x + cross_a : origin_x + axial_position);
      point_positions_xyz[output * 3 + 1] = static_cast<float>(
          rotate ? origin_y + axial_position : origin_y + cross_a);
      point_positions_xyz[output * 3 + 2] =
          static_cast<float>(origin_z + cross_b);
      ++output;
    }
  }
  *point_count = output;
  return 0;
}

CAMPFIRE_API std::int32_t campfire_native_surface_channels(
    const double* const temperature_k,
    const double* const surface_exposure,
    const double* const published_output,
    const std::size_t log_count,
    const std::size_t cells_per_log,
    const std::size_t published_fields_per_log,
    const std::size_t flow_fuel_field,
    const std::size_t flow_smoke_field,
    const double ambient_temperature_k,
    float* const point_fuels,
    float* const point_temperatures,
    float* const point_smokes,
    const std::size_t point_capacity,
    std::size_t* const point_count) {
  if (temperature_k == nullptr || surface_exposure == nullptr ||
      published_output == nullptr || point_fuels == nullptr ||
      point_temperatures == nullptr || point_smokes == nullptr ||
      point_count == nullptr || log_count == 0 || cells_per_log == 0 ||
      published_fields_per_log == 0 ||
      flow_fuel_field >= published_fields_per_log ||
      flow_smoke_field >= published_fields_per_log ||
      !std::isfinite(ambient_temperature_k) || ambient_temperature_k <= 0.0) {
    return 1;
  }

  std::size_t output = 0;
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t log_begin = log_index * cells_per_log;
    const std::size_t published_begin = log_index * published_fields_per_log;
    const double fuel = std::min(
        1.0, std::max(0.0, published_output[published_begin + flow_fuel_field]));
    const double smoke = std::min(
        1.0, std::max(0.0, published_output[published_begin + flow_smoke_field]));
    for (std::size_t local = 0; local < cells_per_log; ++local) {
      const std::size_t cell = log_begin + local;
      if (surface_exposure[cell] <= 0.0) {
        continue;
      }
      if (output >= point_capacity || !std::isfinite(temperature_k[cell])) {
        return 2;
      }
      point_fuels[output] = static_cast<float>(fuel);
      point_temperatures[output] = static_cast<float>(std::min(
          2.0, std::max(0.0, (temperature_k[cell] - ambient_temperature_k) / 500.0)));
      point_smokes[output] = static_cast<float>(smoke);
      ++output;
    }
  }
  *point_count = output;
  return 0;
}
