import logging
import random
import time
from pathlib import Path

# Constants
COOKIES_PATH = Path.home() / ".linkedin_scraper" / "cookies.json"
LINKEDIN_BASE = "https://www.linkedin.com"

# Logger
def setup_logger(name="linkedin_scraper", level=logging.INFO):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = setup_logger()

def human_delay(min_s=1.0, max_s=3.0):
    """Sleep for a random duration to mimic human behavior."""
    time.sleep(random.uniform(min_s, max_s))
