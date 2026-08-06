cmake_minimum_required(VERSION 3.12)
project(campfire_phase6au_native LANGUAGES CXX)

add_library(campfire_wood_native SHARED wood_cell_kernel.cpp)
target_compile_features(campfire_wood_native PRIVATE cxx_std_17)
target_compile_definitions(campfire_wood_native PRIVATE CAMPFIRE_NATIVE_EXPORTS)

if(MSVC)
  target_compile_options(campfire_wood_native PRIVATE /O2 /fp:strict /W4 /EHsc)
else()
  message(FATAL_ERROR "Phase 6AU is pinned to the audited MSVC toolchain")
endif()
