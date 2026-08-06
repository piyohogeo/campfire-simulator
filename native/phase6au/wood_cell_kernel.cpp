#include <algorithm>
#include <cstddef>
#include <cstdint>

#if defined(_WIN32) && defined(CAMPFIRE_NATIVE_EXPORTS)
#define CAMPFIRE_API extern "C" __declspec(dllexport)
#else
#define CAMPFIRE_API extern "C"
#endif

namespace {
constexpr std::int32_t kWetWood = 0;
constexpr std::int32_t kDryWood = 1;
constexpr std::int32_t kPyrolyzing = 2;
constexpr std::int32_t kChar = 3;
constexpr std::int32_t kAsh = 4;
constexpr std::int32_t kDepleted = 5;

std::int32_t classify_phase(
    const double temperature_k,
    const double moisture_mass_kg,
    const double dry_wood_mass_kg,
    const double char_mass_kg,
    const double ash_mass_kg,
    const double pyrolysis_start_temperature_k,
    const double mass_epsilon_kg) {
  if (moisture_mass_kg + dry_wood_mass_kg + char_mass_kg + ash_mass_kg <=
      mass_epsilon_kg) {
    return kDepleted;
  }
  if (char_mass_kg > dry_wood_mass_kg && char_mass_kg > ash_mass_kg) {
    return kChar;
  }
  if (ash_mass_kg > dry_wood_mass_kg + char_mass_kg) {
    return kAsh;
  }
  if (temperature_k >= pyrolysis_start_temperature_k &&
      dry_wood_mass_kg > mass_epsilon_kg) {
    return kPyrolyzing;
  }
  if (moisture_mass_kg > dry_wood_mass_kg * 0.01) {
    return kWetWood;
  }
  return kDryWood;
}
}  // namespace

CAMPFIRE_API std::int32_t campfire_native_abi_version() { return 1; }

CAMPFIRE_API std::int32_t campfire_native_msvc_version() {
#if defined(_MSC_VER)
  return _MSC_VER;
#else
  return 0;
#endif
}

CAMPFIRE_API std::int64_t campfire_native_msvc_full_version() {
#if defined(_MSC_FULL_VER)
  return _MSC_FULL_VER;
#else
  return 0;
#endif
}

CAMPFIRE_API std::int32_t campfire_native_step(
    const std::size_t cell_count,
    double* const temperature_k,
    double* const moisture_mass_kg,
    double* const dry_wood_mass_kg,
    double* const char_mass_kg,
    double* const ash_mass_kg,
    const double* const external_area_m2,
    const double* const surface_exposure,
    const double* const dry_specific_heat_j_kg_k,
    std::int32_t* const phase_code,
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
    const double pyrolysis_start_temperature_k,
    const double mass_epsilon_kg) {
  if (temperature_k == nullptr || moisture_mass_kg == nullptr ||
      dry_wood_mass_kg == nullptr || char_mass_kg == nullptr ||
      ash_mass_kg == nullptr || external_area_m2 == nullptr ||
      surface_exposure == nullptr || dry_specific_heat_j_kg_k == nullptr ||
      phase_code == nullptr || cell_count == 0) {
    return 1;
  }

  const double ambient_squared = ambient_temperature_k * ambient_temperature_k;
  const double ambient_fourth = ambient_squared * ambient_squared;
  for (std::size_t index = 0; index < cell_count; ++index) {
    const double moisture = std::max(0.0, moisture_mass_kg[index]);
    const double dry_wood = std::max(0.0, dry_wood_mass_kg[index]);
    const double char_mass = std::max(0.0, char_mass_kg[index]);
    const double ash_mass = std::max(0.0, ash_mass_kg[index]);
    const double heat_capacity_j_k = std::max(
        dry_wood * dry_specific_heat_j_kg_k[index] +
            moisture * water_specific_heat_j_kg_k +
            char_mass * char_specific_heat_j_kg_k +
            ash_mass * ash_specific_heat_j_kg_k,
        1.0e-9);
    const double area_m2 = external_area_m2[index] * surface_exposure[index];
    const double temperature_squared = temperature_k[index] * temperature_k[index];
    const double external_heat_w =
        heat_flux_w_m2 * radiant_absorptivity * area_m2;
    const double convective_loss_w = convection_w_m2_k * area_m2 *
                                     (temperature_k[index] - ambient_temperature_k);
    const double radiation_loss_w = emissivity * sigma_w_m2_k4 * area_m2 *
                                    (temperature_squared * temperature_squared -
                                     ambient_fourth);
    temperature_k[index] +=
        (external_heat_w - convective_loss_w - radiation_loss_w) * dt_seconds /
        heat_capacity_j_k;
    temperature_k[index] = std::min(
        max_temperature_k,
        std::max(ambient_temperature_k, temperature_k[index]));
    moisture_mass_kg[index] = moisture;
    dry_wood_mass_kg[index] = dry_wood;
    char_mass_kg[index] = char_mass;
    ash_mass_kg[index] = ash_mass;
    phase_code[index] = classify_phase(
        temperature_k[index], moisture, dry_wood, char_mass, ash_mass,
        pyrolysis_start_temperature_k, mass_epsilon_kg);
  }
  return 0;
}

