cmake_minimum_required(VERSION 3.20)
project(KinectHoardNative360 C)

if(NOT DEFINED FREENECT_INCLUDE_DIR OR NOT DEFINED FREENECT_LIBRARY)
  message(FATAL_ERROR "Set FREENECT_INCLUDE_DIR and FREENECT_LIBRARY to a libfreenect build")
endif()

add_library(KinectHoard.Native360 SHARED Native360.c)
target_include_directories(KinectHoard.Native360 PRIVATE "${FREENECT_INCLUDE_DIR}")
target_link_libraries(KinectHoard.Native360 PRIVATE "${FREENECT_LIBRARY}")
target_compile_definitions(KinectHoard.Native360 PRIVATE WIN32_LEAN_AND_MEAN)
