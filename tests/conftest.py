from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# ci replays the same examples each run; HYPOTHESIS_PROFILE=deep explores new ones
SLOW = [HealthCheck.too_slow, HealthCheck.data_too_large]
settings.register_profile("ci", max_examples=300, deadline=None, derandomize=True, suppress_health_check=SLOW)
settings.register_profile("deep", max_examples=5000, deadline=None, suppress_health_check=SLOW)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
