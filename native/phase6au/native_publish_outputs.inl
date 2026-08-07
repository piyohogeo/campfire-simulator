CAMPFIRE_API std::int32_t campfire_native_publish_outputs(
    const std::size_t cell_count,
    const double* const temperature_k,
    const double* const moisture_mass_kg,
    const double* const dry_wood_mass_kg,
    const double* const char_mass_kg,
    const double* const ash_mass_kg,
    const double* const surface_exposure,
    const std::size_t log_count,
    const std::size_t cells_per_log,
    const std::size_t cells_per_section,
    const double* const initial_mass_kg,
    const double* const initial_section_dry_mass_kg,
    const double* const step_output,
    double* const published_output,
    const double dt_seconds,
    const double ambient_temperature_k,
    const double reference_fuel_rate_kg_s,
    const double char_strength_factor) {
  constexpr std::size_t kStepFieldCount = 9;
  constexpr std::size_t kPublishedFieldCount = 11;
  if (temperature_k == nullptr || moisture_mass_kg == nullptr ||
      dry_wood_mass_kg == nullptr || char_mass_kg == nullptr ||
      ash_mass_kg == nullptr || surface_exposure == nullptr ||
      initial_mass_kg == nullptr || initial_section_dry_mass_kg == nullptr ||
      step_output == nullptr || published_output == nullptr || cell_count == 0 ||
      log_count == 0 || cells_per_log == 0 || cells_per_section == 0 ||
      log_count * cells_per_log != cell_count ||
      cells_per_log % cells_per_section != 0 || dt_seconds <= 0.0 ||
      reference_fuel_rate_kg_s <= 0.0) {
    return 1;
  }

  const std::size_t section_count = cells_per_log / cells_per_section;
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t begin = log_index * cells_per_log;
    const std::size_t end = begin + cells_per_log;
    double surface_temperature_sum = 0.0;
    std::size_t surface_cell_count = 0;
    double moisture_total = 0.0;
    double dry_total = 0.0;
    double char_total = 0.0;
    double ash_total = 0.0;
    for (std::size_t index = begin; index < end; ++index) {
      if (surface_exposure[index] > 0.0) {
        surface_temperature_sum += temperature_k[index];
        ++surface_cell_count;
      }
      moisture_total += moisture_mass_kg[index];
      dry_total += dry_wood_mass_kg[index];
      char_total += char_mass_kg[index];
      ash_total += ash_mass_kg[index];
    }
    if (surface_cell_count == 0 || initial_mass_kg[log_index] <= 0.0 ||
        initial_section_dry_mass_kg[log_index] <= 0.0) {
      return 2;
    }

    double weakest_support_ratio = 1.0;
    const std::size_t first_section = section_count > 2 ? 1 : 0;
    const std::size_t last_section = section_count > 2 ? section_count - 1 : section_count;
    for (std::size_t section = first_section; section < last_section; ++section) {
      const std::size_t section_begin = begin + section * cells_per_section;
      const std::size_t section_end = section_begin + cells_per_section;
      double section_dry = 0.0;
      double section_char = 0.0;
      for (std::size_t index = section_begin; index < section_end; ++index) {
        section_dry += dry_wood_mass_kg[index];
        section_char += char_mass_kg[index];
      }
      const double raw_ratio =
          (section_dry + char_strength_factor * section_char) /
          initial_section_dry_mass_kg[log_index];
      const double ratio = std::min(1.0, std::max(0.0, raw_ratio));
      weakest_support_ratio = std::min(weakest_support_ratio, ratio);
    }

    const std::size_t step = log_index * kStepFieldCount;
    const double pyrolysis_gas_rate_kg_s = step_output[step + 1] / dt_seconds;
    const double char_gas_rate_kg_s = step_output[step + 2] / dt_seconds;
    const double flow_fuel =
        std::min(1.0, pyrolysis_gas_rate_kg_s / reference_fuel_rate_kg_s);
    const double surface_mean_temperature_k =
        surface_temperature_sum / static_cast<double>(surface_cell_count);
    const double flow_temperature = std::min(
        2.0,
        std::max(0.0, (surface_mean_temperature_k - ambient_temperature_k) / 500.0));
    const double flow_smoke =
        std::min(1.0, 0.25 * flow_fuel + 5.0 * char_gas_rate_kg_s);
    const std::size_t output = log_index * kPublishedFieldCount;
    published_output[output] = surface_mean_temperature_k;
    published_output[output + 1] = moisture_total;
    published_output[output + 2] = dry_total;
    published_output[output + 3] = char_total;
    published_output[output + 4] = ash_total;
    published_output[output + 5] =
        (moisture_total + dry_total + char_total + ash_total) /
        initial_mass_kg[log_index];
    published_output[output + 6] = weakest_support_ratio;
    published_output[output + 7] = flow_fuel;
    published_output[output + 8] = flow_temperature;
    published_output[output + 9] = flow_smoke;
    published_output[output + 10] = pyrolysis_gas_rate_kg_s;
  }
  return 0;
}
