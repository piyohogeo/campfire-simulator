namespace {
constexpr std::size_t kVisualSurfaceColumns = 24;
constexpr std::size_t kVisualSurfaceRows = 15;
constexpr std::size_t kVisualSurfaceCells =
    kVisualSurfaceColumns * kVisualSurfaceRows;

float visual_clamp01(const float value) {
  return std::min(1.0f, std::max(0.0f, value));
}

std::uint8_t visual_unorm8(const float value) {
  return static_cast<std::uint8_t>(
      std::nearbyint(visual_clamp01(value) * 255.0f));
}

float visual_mix(const float left, const float right, const float amount) {
  return left + (right - left) * amount;
}
}  // namespace

CAMPFIRE_API std::int32_t campfire_native_wood_visual_rgba8_pack(
    const float* const temperatures,
    const float* const moistures,
    const float* const chars,
    const float* const ashes,
    const std::size_t log_count,
    const std::size_t points_per_log,
    const std::uint32_t* const render_slots,
    const std::size_t render_slot_capacity,
    const std::size_t tile_columns,
    const std::size_t tile_rows,
    std::uint8_t* const base_rgba8,
    const std::size_t base_capacity,
    std::uint8_t* const emission_rgba8,
    const std::size_t emission_capacity) {
  constexpr float kDry[3] = {0.30f, 0.12f, 0.045f};
  constexpr float kWet[3] = {0.105f, 0.070f, 0.050f};
  constexpr float kVisualChar[3] = {0.025f, 0.022f, 0.020f};
  constexpr float kVisualAsh[3] = {0.68f, 0.66f, 0.62f};
  constexpr float kLow[3] = {0.06f, 0.001f, 0.0f};
  constexpr float kMid[3] = {0.65f, 0.035f, 0.002f};
  constexpr float kHigh[3] = {1.0f, 0.36f, 0.018f};
  constexpr float kWhite[3] = {1.0f, 0.85f, 0.55f};
  if (temperatures == nullptr || moistures == nullptr || chars == nullptr ||
      ashes == nullptr || render_slots == nullptr || base_rgba8 == nullptr ||
      emission_rgba8 == nullptr || log_count == 0 ||
      points_per_log != kVisualSurfaceCells || tile_columns == 0 ||
      tile_rows == 0 || render_slot_capacity != tile_columns * tile_rows) {
    return 1;
  }
  const std::size_t atlas_pixels = render_slot_capacity * points_per_log;
  const std::size_t atlas_bytes = atlas_pixels * 4;
  if (base_capacity < atlas_bytes || emission_capacity < atlas_bytes) {
    return 2;
  }
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    if (render_slots[log_index] >= render_slot_capacity) {
      return 3;
    }
  }

  const std::uint8_t neutral[] = {
      visual_unorm8(kDry[0]), visual_unorm8(kDry[1]),
      visual_unorm8(kDry[2]), visual_unorm8(0.62f)};
  for (std::size_t pixel = 0; pixel < atlas_pixels; ++pixel) {
    const std::size_t output = pixel * 4;
    base_rgba8[output] = neutral[0];
    base_rgba8[output + 1] = neutral[1];
    base_rgba8[output + 2] = neutral[2];
    base_rgba8[output + 3] = neutral[3];
    emission_rgba8[output] = 0;
    emission_rgba8[output + 1] = 0;
    emission_rgba8[output + 2] = 0;
    emission_rgba8[output + 3] = 255;
  }

  const std::size_t atlas_width = tile_columns * kVisualSurfaceColumns;
  for (std::size_t log_index = 0; log_index < log_count; ++log_index) {
    const std::size_t slot = render_slots[log_index];
    const std::size_t tile_x = slot % tile_columns;
    const std::size_t tile_y = slot / tile_columns;
    for (std::size_t local = 0; local < points_per_log; ++local) {
      const std::size_t input = log_index * points_per_log + local;
      const float temperature = temperatures[input];
      const float moisture = moistures[input];
      const float char_mass = chars[input];
      const float ash_mass = ashes[input];
      if (!std::isfinite(temperature) || temperature <= 0.0 ||
          !std::isfinite(moisture) || moisture < 0.0 ||
          !std::isfinite(char_mass) || char_mass < 0.0 ||
          !std::isfinite(ash_mass) || ash_mass < 0.0) {
        return 4;
      }
      const float wet_amount = visual_clamp01(moisture / 0.030f);
      const float char_amount = visual_clamp01(char_mass / 0.015f);
      const float ash_amount = visual_clamp01(ash_mass / 0.0015f);
      float color[3];
      for (std::size_t channel = 0; channel < 3; ++channel) {
        color[channel] = visual_mix(kDry[channel], kWet[channel], wet_amount);
        color[channel] =
            visual_mix(color[channel], kVisualChar[channel], char_amount);
        color[channel] =
            visual_mix(color[channel], kVisualAsh[channel], ash_amount);
      }
      float roughness = visual_mix(0.62f, 0.43f, wet_amount);
      roughness = visual_mix(roughness, 0.86f, char_amount);
      roughness = visual_mix(roughness, 0.98f, ash_amount);

      float glow[3] = {0.0f, 0.0f, 0.0f};
      const float* glow_left = nullptr;
      const float* glow_right = nullptr;
      float glow_amount = 0.0f;
      if (temperature >= 650.0f && temperature < 800.0f) {
        glow_left = kLow;
        glow_right = kMid;
        glow_amount = (temperature - 650.0f) / 150.0f;
      } else if (temperature >= 800.0f && temperature < 1000.0f) {
        glow_left = kMid;
        glow_right = kHigh;
        glow_amount = (temperature - 800.0f) / 200.0f;
      } else if (temperature >= 1000.0f) {
        glow_left = kHigh;
        glow_right = kWhite;
        glow_amount = visual_clamp01((temperature - 1000.0f) / 300.0f);
      }
      if (glow_left != nullptr) {
        for (std::size_t channel = 0; channel < 3; ++channel) {
          glow[channel] =
              visual_mix(glow_left[channel], glow_right[channel], glow_amount) *
              (1.0f - 0.85f * ash_amount);
        }
      }

      const std::size_t local_y = local / kVisualSurfaceColumns;
      const std::size_t local_x = local % kVisualSurfaceColumns;
      const std::size_t pixel =
          (tile_y * kVisualSurfaceRows + local_y) * atlas_width +
          tile_x * kVisualSurfaceColumns + local_x;
      const std::size_t output = pixel * 4;
      for (std::size_t channel = 0; channel < 3; ++channel) {
        base_rgba8[output + channel] = visual_unorm8(color[channel]);
        emission_rgba8[output + channel] = visual_unorm8(glow[channel]);
      }
      base_rgba8[output + 3] = visual_unorm8(roughness);
      emission_rgba8[output + 3] = 255;
    }
  }
  return 0;
}
