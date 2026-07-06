RINEX 3.05 toolkit for UM982 / Unicore BIN recordings
======================================================

This toolkit converts archived recording folders directly to RINEX 3.05.

It does not use UPrecise.

Main command:

  python scripts/converting/to_rinex/rinex305_toolkit/rinex305_toolkit/rinex305_conversion_full.py 20260503_132939Z_test_log_1

The converter reads from:

  out/<recording>/original/

and writes to:

  out/<recording>/rinex/

Generated files:

  <basename>.yyO   RINEX 3.05 observations
  <basename>.yyP   mixed GNSS NAV
  <basename>.yyN   GPS NAV
  <basename>.yyG   GLONASS NAV
  <basename>.yyC   BeiDou NAV
  <basename>.yyL   Galileo NAV
  <basename>_conversion_report.txt

Files:

  rinex305_conversion_full.py        Direct OBS + NAV converter
  unicore_rangecmp_to_rinex_obs.py   Direct RANGECMPB -> RINEX OBS helper
  trim_unicore_complete_packets.py   Removes incomplete/cut-off packets

Useful options:

  --legacy-bds-codes
      Use C1C/C3C-style BeiDou observation codes instead of the standard C2I/C6I mapping.

  --include-all-nav
      Keep old navigation records from receiver memory instead of filtering to the observation GPS week.

  --zip
      Also create a zip containing generated RINEX files.

The converter normally infers GPS week from the recording. Use --date or --gps-week
only as manual overrides if inference fails.
