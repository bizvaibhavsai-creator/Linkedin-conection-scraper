import csv
import random
import re
import time

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from .auth import load_cookies, login_interactive, login_with_cookies, save_cookies
from .utils import LINKEDIN_BASE, human_delay, logger


def launch_browser(pw, headless=False):
    """Launch Chromium with anti-detection args."""
    browser = pw.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    return browser


def apply_stealth(page):
    """Apply stealth patches to reduce automation detection."""
    Stealth().apply_stealth_sync(page)


def extract_username(profile_url):
    """Extract LinkedIn username from a profile URL."""
    match = re.search(r"linkedin\.com/in/([^/?#]+)", profile_url)
    if not match:
        raise ValueError(f"Invalid LinkedIn profile URL: {profile_url}")
    return match.group(1).strip("/")


def navigate_to_connections(page, profile_url):
    """Navigate to the target profile's connections page.

    Returns the page type: 'search' (other user) or 'own' (own connections).
    Raises PermissionError if connections are not visible.
    """
    username = extract_username(profile_url)

    # Navigate to the profile page
    page.goto(f"{LINKEDIN_BASE}/in/{username}/", wait_until="domcontentloaded", timeout=20000)
    human_delay(3, 5)

    # Check if profile exists
    if "404" in page.title() or page.query_selector("h1.not-found"):
        raise ValueError(f"Profile not found: {username}")

    # Look for the connections link on the profile
    connections_link = page.query_selector(
        'a[href*="/search/results/people"][href*="network"]'
    )

    if not connections_link:
        # Try alternative selectors
        connections_link = page.query_selector(
            'a[href*="connectionOf"]'
        )

    if not connections_link:
        # Try clicking on the connections count text
        connections_link = page.query_selector(
            'li.text-body-small a[href*="connections"], '
            'span.t-bold + span.t-normal'
        )

    if not connections_link:
        raise PermissionError(
            f"Connections are not visible for this profile ({username}). "
            "The profile may be private or connections are hidden."
        )

    # Click the connections link
    connections_link.click()
    human_delay(3, 5)

    logger.info(f"Navigated to connections page for {username}")
    return "search"


def parse_visible_cards(page):
    """Extract connection data from currently visible cards on the page."""
    connections = []

    # Search results page selectors (when viewing someone else's connections)
    card_selectors = [
        "li.reusable-search__result-container",
        "div.entity-result",
        "li.search-result",
    ]

    cards = []
    for selector in card_selectors:
        cards = page.query_selector_all(selector)
        if cards:
            break

    if not cards:
        # Try a broader selector
        cards = page.query_selector_all('[data-chameleon-result-urn]')

    for card in cards:
        try:
            # Extract name
            name_el = card.query_selector(
                'span.entity-result__title-text a span[aria-hidden="true"], '
                'span.entity-result__title-text span[dir="ltr"] span[aria-hidden="true"], '
                'a.app-aware-link span[aria-hidden="true"]'
            )
            name = name_el.inner_text().strip() if name_el else None

            if not name:
                continue

            # Extract profile URL
            link_el = card.query_selector(
                'a.app-aware-link[href*="/in/"], '
                'span.entity-result__title-text a[href*="/in/"]'
            )
            profile_url = ""
            if link_el:
                href = link_el.get_attribute("href") or ""
                if href.startswith("/"):
                    href = LINKEDIN_BASE + href
                # Clean tracking params
                profile_url = href.split("?")[0]

            # Extract headline
            headline_el = card.query_selector(
                'div.entity-result__primary-subtitle, '
                'div.linked-area div.t-14.t-normal, '
                'p.entity-result__summary'
            )
            headline = headline_el.inner_text().strip() if headline_el else ""

            # Extract location
            location_el = card.query_selector(
                'div.entity-result__secondary-subtitle, '
                'div.linked-area div.t-14.t-normal.t-black--light'
            )
            location = location_el.inner_text().strip() if location_el else ""

            connections.append({
                "name": name,
                "headline": headline,
                "profile_url": profile_url,
                "location": location,
            })

        except Exception as e:
            logger.debug(f"Error parsing card: {e}")
            continue

    return connections


def scroll_and_collect(page, progress_callback=None):
    """Scroll through the connections page and collect all visible connections."""
    all_connections = []
    seen_urls = set()
    no_new_count = 0
    max_no_new = 5  # Stop after 5 scrolls with no new results

    logger.info("Starting to collect connections...")

    while no_new_count < max_no_new:
        # Parse currently visible cards
        new_items = parse_visible_cards(page)

        added = 0
        for item in new_items:
            key = item["profile_url"] or item["name"]
            if key not in seen_urls:
                seen_urls.add(key)
                all_connections.append(item)
                added += 1

        if added == 0:
            no_new_count += 1
        else:
            no_new_count = 0

        # Report progress
        if progress_callback:
            progress_callback(len(all_connections))

        logger.info(f"Collected {len(all_connections)} connections so far...")

        # Check for "No results" message
        no_results = page.query_selector(
            'div.search-reusable-search-no-results, '
            'h2.search-no-results__message'
        )
        if no_results:
            logger.info("Reached end of results.")
            break

        # Scroll down with slight randomization
        scroll_factor = random.uniform(0.7, 1.0)
        page.evaluate(f"window.scrollBy(0, window.innerHeight * {scroll_factor})")
        human_delay(1.5, 3.0)

        # Check for "Show more results" button and click it
        show_more = page.query_selector(
            'button.scaffold-finite-scroll__load-button, '
            'button[aria-label="Show more results"]'
        )
        if show_more:
            show_more.click()
            human_delay(2, 4)

    logger.info(f"Finished collecting. Total: {len(all_connections)} connections.")
    return all_connections


def run(profile_url, auth_method="browser", cookie_string=None, headless=False, progress_callback=None):
    """Main scraper orchestrator. Returns list of connection dicts."""
    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=headless)

        try:
            # Authenticate
            if auth_method == "cookies" and cookie_string:
                context = login_with_cookies(browser, cookie_string)
            else:
                context = load_cookies(browser)
                if context is None:
                    context = login_interactive(browser)

            page = context.pages[0] if context.pages else context.new_page()
            apply_stealth(page)

            # Navigate to connections
            navigate_to_connections(page, profile_url)

            # Scroll and collect
            connections = scroll_and_collect(page, progress_callback)

            # Refresh saved session
            save_cookies(context)

            return connections

        except PermissionError:
            raise
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            raise
        finally:
            browser.close()
