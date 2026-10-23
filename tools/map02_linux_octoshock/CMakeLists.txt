cmake_minimum_required(VERSION 3.20)
project(VhMap02OctoshockLinuxProbe LANGUAGES CXX)

if(NOT DEFINED OCTOSH_SOURCE_DIR OR NOT IS_DIRECTORY "${OCTOSH_SOURCE_DIR}")
  message(FATAL_ERROR "OCTOSH_SOURCE_DIR must point at the pinned BizHawk psx/octoshock source tree")
endif()

file(STRINGS "${CMAKE_CURRENT_LIST_DIR}/source-manifest.txt" OCTOSH_RELATIVE_SOURCES REGEX "^[^#].+")
if(NOT OCTOSH_RELATIVE_SOURCES)
  message(FATAL_ERROR "pinned Octoshock source manifest is empty")
endif()

set(OCTOSH_SOURCES)
foreach(relative_source IN LISTS OCTOSH_RELATIVE_SOURCES)
  if(relative_source MATCHES "(^|/)\\.\\.(/|$)" OR IS_ABSOLUTE "${relative_source}")
    message(FATAL_ERROR "source manifest path escapes pinned Octoshock root: ${relative_source}")
  endif()
  set(source_file "${OCTOSH_SOURCE_DIR}/${relative_source}")
  if(NOT EXISTS "${source_file}")
    message(FATAL_ERROR "manifest source missing from pinned tree: ${relative_source}")
  endif()
  list(APPEND OCTOSH_SOURCES "${source_file}")
endforeach()

if(NOT OCTOSH_RELATIVE_SOURCES_LENGTH)
  list(LENGTH OCTOSH_SOURCES OCTOSH_RELATIVE_SOURCES_LENGTH)
endif()
if(NOT OCTOSH_RELATIVE_SOURCES_LENGTH EQUAL 41)
  message(FATAL_ERROR "expected the exact 41 source files from BizHawk 2.11's upstream VS project")
endif()

add_library(octoshock SHARED ${OCTOSH_SOURCES})
target_include_directories(octoshock PRIVATE "${OCTOSH_SOURCE_DIR}")
target_compile_definitions(octoshock PRIVATE EW_EXPORT WANT_LEC_CHECK)
target_compile_features(octoshock PRIVATE cxx_std_14)
target_compile_options(octoshock PRIVATE
  -fPIC
  -fvisibility=hidden
  -fsigned-char
  -fno-strict-aliasing
  -Wall
  -Wextra
)
target_link_options(octoshock PRIVATE -Wl,--no-undefined)
set_target_properties(octoshock PROPERTIES
  OUTPUT_NAME "octoshock.dll"
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN YES
)
