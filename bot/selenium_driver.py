import random
import shutil
import subprocess
import time
from typing import Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from bot.logger import setup_logger

logger = setup_logger(__name__)

# A small pool of realistic desktop user-agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# ---------------------------------------------------------------------------
# Known browser / driver binary locations (checked in order)
# ---------------------------------------------------------------------------

# (browser_binary, chromedriver_binary) pairs that are known to be compatible.
# Snap Chromium ships its own chromedriver — they MUST be used together.
_KNOWN_PAIRS = [
    # Snap Chromium (Ubuntu 22.04+) — browser and driver must come from the same snap
    ("/snap/bin/chromium",              "/snap/bin/chromium.chromedriver"),
    # Snap alternative paths
    ("/snap/chromium/current/usr/bin/chromium",
     "/snap/chromium/current/usr/lib/chromium-browser/chromedriver"),
    # Debian/Ubuntu apt package (20.04)
    ("/usr/bin/chromium-browser",       "/usr/lib/chromium-browser/chromedriver"),
    # Debian/Ubuntu apt package (22.04 non-snap)
    ("/usr/bin/chromium",               "/usr/bin/chromedriver"),
    # Google Chrome (Debian package)
    ("/usr/bin/google-chrome-stable",   None),   # driver resolved separately
    ("/usr/bin/google-chrome",          None),
]

# Standalone driver candidates (used when browser is found but driver is None above)
_DRIVER_CANDIDATES = [
    "chromedriver",
    "chromium-chromedriver",
    "chromium.chromedriver",
]

# Standalone browser candidates (fallback)
_BROWSER_CANDIDATES = [
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
]


def _binary_exists(path: str) -> bool:
    """Return True if *path* is an executable file."""
    import os
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _find_on_path(candidates: list) -> Optional[str]:
    """Return the first candidate found on PATH, or None."""
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def _get_version(binary: str) -> Optional[str]:
    """Return the full version string of a Chrome/Chromium binary, or None."""
    try:
        out = subprocess.check_output(
            [binary, "--version"], stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return out
    except Exception:
        return None


def _resolve_browser_and_driver(
    explicit_browser: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (browser_binary, chromedriver_binary).

    Strategy (in order):
    1. If the user supplied an explicit browser path, use it and find a
       matching driver.
    2. Walk the known (browser, driver) pairs and return the first where
       both binaries exist.
    3. Search PATH for any browser candidate and any driver candidate
       independently (last resort — may mismatch on snap systems).
    """
    # --- 1. Explicit browser path ---
    if explicit_browser and _binary_exists(explicit_browser):
        driver = _find_on_path(_DRIVER_CANDIDATES)
        logger.info(f"Using explicit browser: {explicit_browser}")
        if driver:
            logger.info(f"ChromeDriver: {driver}")
        return explicit_browser, driver

    # --- 2. Known compatible pairs ---
    for browser, driver in _KNOWN_PAIRS:
        if _binary_exists(browser):
            if driver is None:
                # Browser found but driver not specified — search PATH
                driver = _find_on_path(_DRIVER_CANDIDATES)
            if driver and _binary_exists(driver):
                logger.info(f"Browser binary : {browser}")
                logger.info(f"ChromeDriver   : {driver}")
                ver = _get_version(browser)
                if ver:
                    logger.info(f"Browser version: {ver}")
                return browser, driver
            elif driver is None:
                # Browser found, no driver anywhere — return browser only
                # (will fall back to webdriver-manager)
                logger.info(f"Browser binary : {browser}")
                ver = _get_version(browser)
                if ver:
                    logger.info(f"Browser version: {ver}")
                return browser, None

    # --- 3. PATH search (independent) ---
    browser = _find_on_path(_BROWSER_CANDIDATES)
    driver = _find_on_path(_DRIVER_CANDIDATES)

    if browser:
        logger.info(f"Browser binary : {browser}")
        ver = _get_version(browser)
        if ver:
            logger.info(f"Browser version: {ver}")
    else:
        logger.warning(
            "No Chrome/Chromium binary found. "
            "Install with: sudo apt install -y chromium chromium-driver"
        )

    if driver:
        logger.info(f"ChromeDriver   : {driver}")
    else:
        logger.warning(
            "No chromedriver found. "
            "Install with: sudo apt install -y chromium-driver"
        )

    return browser, driver


class SeleniumDriver:
    """Wrapper for Selenium WebDriver with Chromium/Chrome.

    Handles snap Chromium, apt Chromium, and Google Chrome automatically.
    The snap version of Chromium ships its own chromedriver — this class
    detects and uses the matching pair so versions never mismatch.
    """

    def __init__(self, headless: bool = True, proxy: Optional[str] = None,
                 chromium_path: Optional[str] = None):
        self.headless = headless
        self.proxy = proxy
        self.chromium_path = chromium_path
        self.driver = None
        self._setup_driver()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _build_options(self) -> Options:
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")
            logger.info("Running in headless mode")

        # Required for running as root / in Docker / on servers
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--window-size=1920,1080")
        # Suppress "Chrome is being controlled by automated software" bar
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Rotate user-agent
        ua = random.choice(USER_AGENTS)
        options.add_argument(f"--user-agent={ua}")
        logger.debug(f"User-agent: {ua}")

        if self.proxy:
            logger.info(f"Setting proxy: {self.proxy}")
            options.add_argument(f"--proxy-server={self.proxy}")

        return options

    def _setup_driver(self):
        options = self._build_options()
        browser_bin, driver_bin = _resolve_browser_and_driver(self.chromium_path)

        # Tell Selenium which browser binary to use
        if browser_bin:
            options.binary_location = browser_bin

        try:
            if driver_bin:
                service = Service(driver_bin)
            else:
                # Fall back to webdriver-manager (requires internet access)
                logger.warning(
                    "No system chromedriver found — falling back to webdriver-manager. "
                    "This requires internet access."
                )
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    try:
                        from webdriver_manager.core.os_manager import ChromeType
                        service = Service(
                            ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                        )
                    except Exception:
                        service = Service(ChromeDriverManager().install())
                except ImportError:
                    raise RuntimeError(
                        "chromedriver not found and webdriver-manager is not installed.\n"
                        "Fix: sudo apt install -y chromium-driver"
                    )

            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Selenium WebDriver initialised successfully")

        except Exception as e:
            logger.error(
                f"WebDriver initialisation failed: {e}\n"
                "Quick fix for Ubuntu with snap Chromium:\n"
                "  sudo snap install chromium          # installs browser + driver together\n"
                "  chromium --version                  # verify\n"
                "  chromium.chromedriver --version     # verify driver matches\n"
                "\n"
                "Quick fix for Ubuntu apt Chromium:\n"
                "  sudo apt install -y chromium chromium-driver\n"
                "\n"
                "Or set 'Chromium Path' in the dashboard to the full path of your browser binary."
            )
            raise

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def get(self, url: str):
        try:
            logger.debug(f"Navigating to: {url}")
            self.driver.get(url)
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            raise

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.debug("WebDriver closed")
