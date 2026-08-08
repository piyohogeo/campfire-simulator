cmake_minimum_required(VERSION 3.12)
project(campfire_phase6di_surface_frame_spike LANGUAGES CXX)

add_library(campfire_surface_frame_spike SHARED surface_frame_spike.cpp)
target_compile_features(campfire_surface_frame_spike PRIVATE cxx_std_17)
target_compile_definitions(campfire_surface_frame_spike PRIVATE CAMPFIRE_SURFACE_FRAME_SPIKE_EXPORTS)

if(MSVC)
  target_compile_options(campfire_surface_frame_spike PRIVATE /O2 /fp:strict /W4 /EHsc)
else()
  message(FATAL_ERROR "Phase 6DI is pinned to the audited MSVC toolchain")
endif()
