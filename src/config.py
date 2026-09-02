"""Central configuration: env loading and study-wide constants."""
import os

from dotenv import load_dotenv

load_dotenv()

TOKENROUTER_API_KEY = os.environ["TOKENROUTER_API_KEY"]
BASE_URL = os.environ.get("TOKENROUTER_BASE_URL", "https://api.tokenrouter.com/v1")
MODEL_SLUG = os.environ.get("MODEL_SLUG", "z-ai/glm-5.3-free")

# z.ai publishes no training-data cutoff for GLM-5.3 / GLM-5.2 (checked 2026-09-02;
# GLM-5.3 released 2026-08-14 on the GLM-5.2 base, post-training scaled through ~Aug 2026).
# We assume a conservative cutoff of 2026-06-01: resolutions dated after this are treated
# as plausibly unseen by the model ("post_cutoff" stratum). This is an assumption, not
# a documented fact; see LIMITATIONS.md.
ASSUMED_CUTOFF = "2026-06-01"

REQUEST_TIMEOUT_S = 180
MAX_ATTEMPTS = 4
RETRY_STATUS = {429, 500, 502, 503, 504}
