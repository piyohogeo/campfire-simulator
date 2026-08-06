CAMPFIRE_API std::int32_t campfire_native_arrhenius_complete_step(
    const std::size_t cell_count,
    double* const temperature_k,
    double* const moisture_mass_kg,
    double* const dry_wood_mass_kg,
    double* const volatile_potential_kg,
    double* const char_mass_kg,
    double* const ash_mass_kg,
    const double* const oxygen_factor,
    const double* const external_area_m2,
    const double* const surface_exposure,
    const double* const dry_specific_heat_j_kg_k,
    std::int32_t* const phase_code,
    const std::size_t pair_count,
    const std::uint32_t* const first_cell,
    const std::uint32_t* const second_cell,
    const double* const conductance_w_k,
    double* const conduction_energy_j,
    double* const heat_capacity_j_k,
    const std::size_t log_count,
    const std::size_t cells_per_log,
    double* const elapsed_seconds,
    double* const cumulative_output,
    double* const step_output,
    const double dt_seconds,
    const double heat_flux_w_m2,
    const double radiant_absorptivity,
    const double convection_w_m2_k,
    const double emissivity,
    const double sigma_w_m2_k4,
    const double ambient_temperature_k,
    const double water_specific_heat_j_kg_k,
    const double char_specific_heat_j_kg_k,
    const double ash_specific_heat_j_kg_k,
    const double max_temperature_k,
    const double evaporation_start_temperature_k,
    const double water_latent_heat_j_kg,
    const double evaporation_max_fraction_s,
    const double pyrolysis_start_temperature_k,
    const double pyrolysis_heat_j_kg,
    const double gas_constant_j_mol_k,
    const double parallel_common_scale,
    const double gas_preexponential_s,
    const double gas_activation_energy_j_mol,
    const double tar_preexponential_s,
    const double tar_activation_energy_j_mol,
    const double char_preexponential_s,
    const double char_activation_energy_j_mol,
    const double secondary_residence_time_s,
    const double secondary_preexponential_s,
    const double secondary_activation_energy_j_mol,
    const double secondary_min_temperature_k,
    const double secondary_max_temperature_k,
    const double char_oxidation_start_temperature_k,
    const double char_oxidation_max_fraction_s,
    const double char_ash_yield,
    const double char_oxidation_heat_j_kg,
    const double mass_epsilon_kg) {
  constexpr std::size_t kStepFieldCount = 9;
  constexpr std::size_t kCumulativeFieldCount = 7;
  if (temperature_k == nullptr || moisture_mass_kg == nullptr ||
      dry_wood_mass_kg == nullptr || volatile_potential_kg == nullptr ||
      char_mass_kg == nullptr || ash_mass_kg == nullptr ||
      oxygen_factor == nullptr || external_area_m2 == nullptr ||
      surface_exposure == nullptr || dry_specific_heat_j_kg_k == nullptr ||
      phase_code == nullptr || first_cell == nullptr || second_cell == nullptr ||
      conductance_w_k == nullptr || conduction_energy_j == nullptr ||
      heat_capacity_j_k == nullptr || elapsed_seconds == nullptr ||
      cumulative_output == nullptr || step_output == nullptr || cell_count == 0 ||
      pair_count == 0 || log_count == 0 || cells_per_log == 0 ||
      log_count * cells_per_log != cell_count || gas_constant_j_mol_k <= 0.0 ||
      parallel_common_scale <= 0.0 || secondary_residence_time_s <= 0.0 ||
      secondary_max_temperature_k < secondary_min_temperature_k) {
    return 1;
  }

  std::fill(conduction_energy_j, conduction_energy_j + cell_count, 0.0);
  std::fill(step_output, step_output + log_count * kStepFieldCount, 0.0);
  for (std::size_t pair_index = 0; pair_index < pair_count; ++pair_index) {
    const std::size_t first = first_cell[pair_index];
    const std::size_t second = second_cell[pair_index];
    if (first >= cell_count || second >= cell_count) {
      return 2;
    }
    const double energy_j = conductance_w_k[pair_index] *
                            (temperature_k[second] - temperature_k[first]) *
                            dt_seconds;
    conduction_energy_j[first] += energy_j;
    conduction_energy_j[second] -= energy_j;
  }

  for (std::size_t index = 0; index < cell_count; ++index) {
    const std::size_t log_index = index / cells_per_log;
    const double moisture = moisture_mass_kg[index];
    const double dry_wood = dry_wood_mass_kg[index];
    const double char_mass = char_mass_kg[index];
    const double ash_mass = ash_mass_kg[index];
    const double capacity = std::max(
        dry_wood * dry_specific_heat_j_kg_k[index] +
            moisture * water_specific_heat_j_kg_k +
            char_mass * char_specific_heat_j_kg_k +
            ash_mass * ash_specific_heat_j_kg_k,
        1.0e-9);
    heat_capacity_j_k[index] = capacity;
    const double area_m2 = external_area_m2[index] * surface_exposure[index];
    if (area_m2 == 0.0) {
      temperature_k[index] += conduction_energy_j[index] / capacity;
      continue;
    }
    const double external_heat_w =
        heat_flux_w_m2 * radiant_absorptivity * area_m2;
    const double convective_loss_w = convection_w_m2_k * area_m2 *
                                     (temperature_k[index] - ambient_temperature_k);
    const double radiation_loss_w = emissivity * sigma_w_m2_k4 * area_m2 *
                                    (std::pow(temperature_k[index], 4.0) -
                                     std::pow(ambient_temperature_k, 4.0));
    step_output[log_index * kStepFieldCount + 3] +=
        external_heat_w * dt_seconds;
    const double net_energy_j = conduction_energy_j[index] +
                                (external_heat_w - convective_loss_w -
                                 radiation_loss_w) *
                                    dt_seconds;
    temperature_k[index] += net_energy_j / capacity;
  }

  for (std::size_t index = 0; index < cell_count; ++index) {
    if (moisture_mass_kg[index] > 0.0 &&
        temperature_k[index] > evaporation_start_temperature_k) {
      const double sensible_excess_j =
          (temperature_k[index] - evaporation_start_temperature_k) *
          heat_capacity_j_k[index];
      const double energy_limited_kg = sensible_excess_j / water_latent_heat_j_kg;
      const double rate_limited_kg = moisture_mass_kg[index] *
                                     evaporation_max_fraction_s * dt_seconds;
      const double evaporated_kg = std::min(
          moisture_mass_kg[index], std::min(energy_limited_kg, rate_limited_kg));
      moisture_mass_kg[index] -= evaporated_kg;
      temperature_k[index] -=
          evaporated_kg * water_latent_heat_j_kg / heat_capacity_j_k[index];
      step_output[(index / cells_per_log) * kStepFieldCount] += evaporated_kg;
    }
  }

  for (std::size_t index = 0; index < cell_count; ++index) {
    if (dry_wood_mass_kg[index] > 0.0) {
      const double moisture_ratio =
          moisture_mass_kg[index] / std::max(dry_wood_mass_kg[index], 1.0e-12);
      const double dryness_factor =
          std::min(1.0, std::max(0.0, 1.0 - moisture_ratio / 0.10));
      const double reciprocal_rt =
          1.0 / (gas_constant_j_mol_k * temperature_k[index]);
      const double gas_rate_s = parallel_common_scale * gas_preexponential_s *
                                std::exp(-gas_activation_energy_j_mol * reciprocal_rt);
      const double tar_rate_s = parallel_common_scale * tar_preexponential_s *
                                std::exp(-tar_activation_energy_j_mol * reciprocal_rt);
      const double char_rate_s = parallel_common_scale * char_preexponential_s *
                                 std::exp(-char_activation_energy_j_mol * reciprocal_rt);
      const double total_rate_s = gas_rate_s + tar_rate_s + char_rate_s;
      const double reacted_fraction =
          1.0 - std::exp(-total_rate_s * dryness_factor * dt_seconds);
      const double rate_limited_kg = dry_wood_mass_kg[index] * reacted_fraction;
      const double pyrolysis_temperature_k = temperature_k[index];
      const double capacity = std::max(
          dry_wood_mass_kg[index] * dry_specific_heat_j_kg_k[index] +
              moisture_mass_kg[index] * water_specific_heat_j_kg_k +
              char_mass_kg[index] * char_specific_heat_j_kg_k +
              ash_mass_kg[index] * ash_specific_heat_j_kg_k,
          1.0e-9);
      const double energy_limited_kg = std::max(
          0.0, (temperature_k[index] - pyrolysis_start_temperature_k) * capacity /
                   pyrolysis_heat_j_kg);
      const double reacted_wood_kg = std::min(
          dry_wood_mass_kg[index], std::min(rate_limited_kg, energy_limited_kg));
      const double gas_created_kg = reacted_wood_kg * gas_rate_s / total_rate_s;
      const double tar_created_kg = reacted_wood_kg * tar_rate_s / total_rate_s;
      const double char_created_kg = reacted_wood_kg * char_rate_s / total_rate_s;
      const double volatile_created_kg = gas_created_kg + tar_created_kg;
      dry_wood_mass_kg[index] -= reacted_wood_kg;
      char_mass_kg[index] += char_created_kg;
      volatile_potential_kg[index] =
          std::max(0.0, volatile_potential_kg[index] - volatile_created_kg);
      temperature_k[index] -= reacted_wood_kg * pyrolysis_heat_j_kg / capacity;

      double secondary_fraction = 0.0;
      if (pyrolysis_temperature_k >= secondary_min_temperature_k) {
        const double bounded_temperature_k =
            std::min(pyrolysis_temperature_k, secondary_max_temperature_k);
        const double secondary_rate_s =
            secondary_preexponential_s *
            std::exp(-secondary_activation_energy_j_mol /
                     (gas_constant_j_mol_k * bounded_temperature_k));
        secondary_fraction =
            1.0 - std::exp(-secondary_rate_s * secondary_residence_time_s);
      }
      const double secondary_tar_cracked_kg =
          tar_created_kg * secondary_fraction;
      const std::size_t output = (index / cells_per_log) * kStepFieldCount;
      step_output[output + 1] += volatile_created_kg;
      step_output[output + 4] += gas_created_kg;
      step_output[output + 5] += tar_created_kg;
      step_output[output + 6] += char_created_kg;
      step_output[output + 7] += secondary_tar_cracked_kg;
      step_output[output + 8] += tar_created_kg - secondary_tar_cracked_kg;
    }
  }

  for (std::size_t index = 0; index < cell_count; ++index) {
    if (char_mass_kg[index] > 0.0 &&
        temperature_k[index] > char_oxidation_start_temperature_k &&
        oxygen_factor[index] > 0.0 && surface_exposure[index] > 0.0) {
      const double temperature_ramp = std::min(
          1.0, std::max(0.0, (temperature_k[index] -
                              char_oxidation_start_temperature_k) /
                                 300.0));
      const double oxidized_char_kg = std::min(
          char_mass_kg[index],
          char_mass_kg[index] * char_oxidation_max_fraction_s *
              temperature_ramp * oxygen_factor[index] * surface_exposure[index] *
              dt_seconds);
      const double ash_created_kg = oxidized_char_kg * char_ash_yield;
      const double char_gas_kg = oxidized_char_kg - ash_created_kg;
      char_mass_kg[index] -= oxidized_char_kg;
      ash_mass_kg[index] += ash_created_kg;
      const double capacity = std::max(
          dry_wood_mass_kg[index] * dry_specific_heat_j_kg_k[index] +
              moisture_mass_kg[index] * water_specific_heat_j_kg_k +
              char_mass_kg[index] * char_specific_heat_j_kg_k +
              ash_mass_kg[index] * ash_specific_heat_j_kg_k,
          1.0e-9);
      temperature_k[index] +=
          oxidized_char_kg * char_oxidation_heat_j_kg / capacity;
      step_output[(index / cells_per_log) * kStepFieldCount + 2] += char_gas_kg;
    }
  }

  for (std::size_t index = 0; index < cell_count; ++index) {
    if (!(temperature_k[index] > ambient_temperature_k)) {
      temperature_k[index] = ambient_temperature_k;
    } else if (temperature_k[index] > max_temperature_k) {
      temperature_k[index] = max_temperature_k;
    }
    if (!(moisture_mass_kg[index] > 0.0)) moisture_mass_kg[index] = 0.0;
    if (!(dry_wood_mass_kg[index] > 0.0)) dry_wood_mass_kg[index] = 0.0;
    if (!(char_mass_kg[index] > 0.0)) char_mass_kg[index] = 0.0;
    if (!(ash_mass_kg[index] > 0.0)) ash_mass_kg[index] = 0.0;
    phase_code[index] = classify_phase(
        temperature_k[index], moisture_mass_kg[index], dry_wood_mass_kg[index],
        char_mass_kg[index], ash_mass_kg[index], pyrolysis_start_temperature_k,
        mass_epsilon_kg);
  }

  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t step = log_index * kStepFieldCount;
    const std::size_t cumulative = log_index * kCumulativeFieldCount;
    elapsed_seconds[log_index] += dt_seconds;
    cumulative_output[cumulative] += step_output[step];
    cumulative_output[cumulative + 1] += step_output[step + 1];
    cumulative_output[cumulative + 2] += step_output[step + 2];
    cumulative_output[cumulative + 3] += step_output[step + 4];
    cumulative_output[cumulative + 4] += step_output[step + 5];
    cumulative_output[cumulative + 5] += step_output[step + 6];
    cumulative_output[cumulative + 6] += step_output[step + 7];
  }
  return 0;
}
