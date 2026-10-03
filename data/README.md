# Legacy processed data

This directory contains the historical processed CSV baseline retained for
regression and audit comparison. Production v2 ingestion writes immutable source
files to `var/platform/raw` and does not read this directory automatically.
