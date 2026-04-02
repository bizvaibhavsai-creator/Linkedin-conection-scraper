import json
import time

from .utils import COOKIES_PATH, LINKEDIN_BASE, human_delay, logger


def save_cookies(context, path=COOKIES_PATH):
    """Save browser session (cookies + localStorage) to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    logger.info(f"Session saved to {path}")


def load_cookies(browser, path=COOKIES_PATH):
    """Load saved session and validate it. Returns BrowserContext or None."""
    if not path.exists():
        logger.info("No saved session found.")
        return None

    context = browser.new_context(
        storage_state=str(path),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    page = context.new_page()

    try:
        page.goto(f"{LINKEDIN_BASE}/feed/", wait_until="domcontentloaded", timeout=15000)
        human_delay(2, 4)

        url = page.url
        if "/login" in url or "/checkpoint" in url:
            logger.warning("Saved session is stale. Will need to re-login.")
            context.close()
            path.unlink(missing_ok=True)
            return None

        logger.info("Saved session is valid.")
        return context
    except Exception as e:
        logger.warning(f"Failed to validate saved session: {e}")
        context.close()
        path.unlink(missing_ok=True)
        return None


def login_interactive(browser):
    """Open browser for manual login. Returns authenticated BrowserContext."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    page = context.new_page()
    page.goto(f"{LINKEDIN_BASE}/login", wait_until="domcontentloaded")

    logger.info("Please log in to LinkedIn in the browser window. Waiting up to 5 minutes...")

    timeout = 300  # 5 minutes
    start = time.time()

    while time.time() - start < timeout:
        url = page.url
        if "/login" not in url and "/checkpoint" not in url:
            logger.info("Login successful!")
            human_delay(2, 3)
            save_cookies(context)
            return context
        time.sleep(3)

    raise TimeoutError("Login timed out after 5 minutes. Please try again.")


def login_with_cookies(browser, cookie_string):
    """Authenticate using provided cookie string. Returns authenticated BrowserContext."""
    cookies = _parse_cookie_string(cookie_string)

    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    context.add_cookies(cookies)

    page = context.new_page()
    page.goto(f"{LINKEDIN_BASE}/feed/", wait_until="domcontentloaded", timeout=15000)
    human_delay(2, 4)

    url = page.url
    if "/login" in url or "/checkpoint" in url:
        context.close()
        raise ValueError("Provided cookies are invalid or expired.")

    logger.info("Cookie authentication successful!")
    save_cookies(context)
    return context


def _parse_cookie_string(cookie_string):
    """Parse cookie string (header format or JSON array) into cookie dicts."""
    cookie_string = cookie_string.strip()

    # Try JSON format first
    if cookie_string.startswith("["):
        try:
            parsed = json.loads(cookie_string)
            cookies = []
            for c in parsed:
                cookies.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ".linkedin.com"),
                    "path": c.get("path", "/"),
                })
            return cookies
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Invalid JSON cookie format: {e}")

    # Header format: "li_at=VALUE; JSESSIONID=VALUE"
    cookies = []
    for pair in cookie_string.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".linkedin.com",
            "path": "/",
        })

    if not cookies:
        raise ValueError("Could not parse any cookies from the provided string.")

    return cookies
