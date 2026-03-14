# Stage 2: Unifying
# Responsible for unit normalisation, range resolution,
# flag computation, deviation calculation, and enriched JSON output.

from .normaliser import normalise_units
from .ranger import resolve_ranges
from .flagger import compute_flags
