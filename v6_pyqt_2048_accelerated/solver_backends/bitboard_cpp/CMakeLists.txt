cmake_minimum_required(VERSION 3.25)
project(bitboard_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  add_compile_options(/O2 /EHsc /utf-8)
endif()

# pybind11：优先用 -Dpybind11_DIR，其次自动从当前 Python 的 pybind11 包探测
find_package(pybind11 CONFIG QUIET)
if(NOT pybind11_FOUND)
  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
  execute_process(
    COMMAND "${Python_EXECUTABLE}" -c "import pybind11; print(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE _pb_dir OUTPUT_STRIP_TRAILING_WHITESPACE)
  list(APPEND CMAKE_PREFIX_PATH "${_pb_dir}")
  find_package(pybind11 CONFIG REQUIRED)
endif()

pybind11_add_module(bitboard_cpp bindings.cpp bitboard.cpp search.cpp)

# 独立自测可执行文件（不依赖 Python）
add_executable(bitboard_tests tests.cpp bitboard.cpp search.cpp)
