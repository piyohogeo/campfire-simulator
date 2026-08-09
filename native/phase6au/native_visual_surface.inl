CAMPFIRE_API std::int32_t campfire_native_visual_surface_pack(
    const double* const temperature_k,
    const double* const moisture_mass_kg,
    const double* const char_mass_kg,
    const double* const ash_mass_kg,
    const double* const surface_exposure,
    const std::size_t log_count,
    const std::size_t cells_per_log,
    float* const temperatures,
    float* const moistures,
    float* const chars,
    float* const ashes,
    std::uint32_t* const local_surface_indices,
    const std::size_t point_capacity,
    std::size_t* const point_count) {
  if (temperature_k == nullptr || moisture_mass_kg == nullptr ||
      char_mass_kg == nullptr || ash_mass_kg == nullptr ||
      surface_exposure == nullptr || temperatures == nullptr ||
      moistures == nullptr || chars == nullptr || ashes == nullptr ||
      local_surface_indices == nullptr || point_count == nullptr ||
      log_count == 0 || cells_per_log == 0) {
    return 1;
  }
  std::size_t output = 0;
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t begin = log_index * cells_per_log;
    std::uint32_t local_surface_index = 0;
    for (std::size_t local_cell = 0; local_cell < cells_per_log; ++local_cell) {
      const std::size_t cell = begin + local_cell;
      if (surface_exposure[cell] <= 0.0) {
        continue;
      }
      const double values[] = {
          temperature_k[cell], moisture_mass_kg[cell],
          char_mass_kg[cell], ash_mass_kg[cell]};
      if (output >= point_capacity || !std::isfinite(values[0]) ||
          values[0] <= 0.0 || !std::isfinite(values[1]) || values[1] < 0.0 ||
          !std::isfinite(values[2]) || values[2] < 0.0 ||
          !std::isfinite(values[3]) || values[3] < 0.0) {
        return 2;
      }
      temperatures[output] = static_cast<float>(values[0]);
      moistures[output] = static_cast<float>(values[1]);
      chars[output] = static_cast<float>(values[2]);
      ashes[output] = static_cast<float>(values[3]);
      local_surface_indices[output] = local_surface_index;
      ++local_surface_index;
      ++output;
    }
  }
  *point_count = output;
  return 0;
}
