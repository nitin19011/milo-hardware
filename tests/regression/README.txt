From the repository root:
  py -3 tests/regression/test_flex_calibration.py

Uses Python's standard library. Replays the 240 measured USB relaxed/fist samples,
checks that the current glove reads all three fingers and requires all three for
its trigger, and checks parity with the current gesture collector.

The packaging validation also compiled the exact production sampling/trigger
functions in a native stub harness and replayed the same trace, including a
middle-only release and ADC-rail fault. See docs/VALIDATION_20261023.json.
These are software checks, not a physical hardware or full AI recognition test.
