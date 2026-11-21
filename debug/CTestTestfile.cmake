# CMake generated Testfile for 
# Source directory: D:/Downloads/PulseMetrics_V2_redesign
# Build directory: D:/Downloads/PulseMetrics_V2_BUILD/debug
# 
# This file includes the relevant testing commands required for 
# testing this directory and lists subdirectories to be tested as well.
add_test("v2_persistence" "D:/Downloads/PulseMetrics_V2_BUILD/debug/bin/test_persistence_v2.exe")
set_tests_properties("v2_persistence" PROPERTIES  TIMEOUT "30" WORKING_DIRECTORY "D:/Downloads/PulseMetrics_V2_BUILD/debug/test-run/persistence" _CMAKE_TEST_BUILD_DEPENDS "D:/Downloads/PulseMetrics_V2_BUILD/debug/bin/test_persistence_v2.exe" _BACKTRACE_TRIPLES "D:/Downloads/PulseMetrics_V2_redesign/CMakeLists.txt;41;add_test;D:/Downloads/PulseMetrics_V2_redesign/CMakeLists.txt;0;")
add_test("v2_contract" "D:/Downloads/PulseMetrics_V2_BUILD/debug/bin/test_contract.exe")
set_tests_properties("v2_contract" PROPERTIES  _CMAKE_TEST_BUILD_DEPENDS "D:/Downloads/PulseMetrics_V2_BUILD/debug/bin/test_contract.exe" _BACKTRACE_TRIPLES "D:/Downloads/PulseMetrics_V2_redesign/CMakeLists.txt;46;add_test;D:/Downloads/PulseMetrics_V2_redesign/CMakeLists.txt;0;")
