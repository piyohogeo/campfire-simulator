# Phase 6GZ post-readback boundary ladder

Phase 6GX and Phase 6GY remain frozen. The primary historical population for
mechanism inference is the 31 unattended Candidate B timeouts; Phase 6GY launch
23 is user-intervention-contaminated and is used only as a boundary reference.

The read-only audit establishes that all primary timeouts returned seven public
handles and left `phase6gl_readback_after` as the last coarse marker. A
47,641,541-byte `p3_f0180_temperature.nvdb` was durable. Given the frozen code
order, schema preflight and the preceding velocity pipeline had therefore been
reached, and temperature save/poll had been reached. The file does not prove
that typed read, ROI sampling, or collector capture completed. The contaminated
launch 23 saved stack points into temperature ROI sampling but cannot establish
a naturally occurring second termination form.

The new ladder preserves the Candidate ordering and adds one temperature
boundary per independent process: qualified Control; temperature-front;
volume; bounded volume metadata; temporary save; typed read; ROI sampling; and
collector capture. Every prefix runs in a fresh process. There are no retries
or replacements, and the first non-normal operation, resource, lifecycle,
identity, or cleanup result stops the phase. The 16/17 GiB limits, 8 GiB host
floors, release-after-close, progress-aware CDB, exact identity cleanup, and
attempt-local temporary-file allowlist remain unchanged.

This is an engineering boundary localization only. It does not restart the
six-hour population, the formal S93/S100/OFF population, other channels, video,
or production integration.
