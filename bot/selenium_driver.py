import os
import random
import shutil
import subprocess
import tempfile
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

# IMPORTANT: Snap Chromium CANNOT be used with Selenium.
# The snap sandbox prevents chromedriver from launching the snap binary
# as a subprocess. Use the apt version instead:
#   sudo snap remove chromium
#   sudo apt install -y chromium-browser chromium-chromedriver   # Ubuntu 20.04
#   sudo apt install -y chromium chromium-driver                 # Ubuntu 22.04+

# (browser_binary, chromedriver_binary) pairs that are known to be compatible.
# NOTE: On Ubuntu 22.04+, /usr/bin/chromium-browser is a STUB that just says
# "install the snap". We must NOT use it. The real apt binary is /usr/bin/chromium.
_KNOWN_PAIRS = [
    # Debian/Ubuntu apt package (22.04+ non-snap) — check BEFORE chromium-browser
    ("/usr/bin/chromium",               "/usr/bin/chromedriver"),
    # Debian/Ubuntu apt package (20.04) — only valid if it's a real binary, not a stub
    ("/usr/bin/chromium-browser",       "/usr/lib/chromium-browser/chromedriver"),
    # Google Chrome (Debian package)
    ("/usr/bin/google-chrome-stable",   None),   # driver resolved separately
    ("/usr/bin/google-chrome",          None),
]

# Snap binary paths — detected to show a helpful error, NOT used for launching
_SNAP_BROWSER_PATHS = [
    "/snap/bin/chromium",
    "/snap/chromium/current/usr/bin/chromium",
]

# Stub script paths — Ubuntu 22.04+ installs these as snap redirectors.
# They are NOT real browsers and must be skipped.
_STUB_PATHS = [
    "/usr/bin/chromium-browser",   # Ubuntu 22.04+ stub → "install snap chromium"
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


def _is_snap_stub(path: str) -> bool:
    """
    Return True if *path* is the Ubuntu 22.04+ snap redirect stub.
    The stub is a shell script that just prints 'install snap chromium'.
    We detect it by reading the first 512 bytes and looking for 'snap'.
    """
    try:
        with open(path, "rb") as fh:
            header = fh.read(512).decode("utf-8", errors="ignore")
        return "snap" in header.lower() and "install" in header.lower()
    except Exception:
        return False


def _binary_exists(path: str) -> bool:
    """Return True if *path* is a real executable (not a snap stub)."""
    if not (bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)):
        return False
    # Skip Ubuntu 22.04+ snap redirect stubs
    if path in _STUB_PATHS and _is_snap_stub(path):
        logger.debug(f"Skipping snap stub: {path}")
        return False
    return True


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


def _get_major_version(binary: str) -> Optional[int]:
    """Return the major version integer of a Chrome/Chromium binary, or None."""
    ver = _get_version(binary)
    if not ver:
        return None
    for part in ver.split():
        if part[0].isdigit():
            try:
                return int(part.split(".")[0])
            except ValueError:
                pass
    return None


def _versions_match(browser_bin: str, driver_bin: str) -> bool:
    """Return True if browser and driver have the same major version."""
    bv = _get_major_version(browser_bin)
    dv = _get_major_version(driver_bin)
    if bv is None or dv is None:
        return True  # can't check — assume OK
    if bv != dv:
        logger.warning(
            f"Version mismatch: browser={bv}, chromedriver={dv}. "
            "Will use webdriver-manager to download the correct driver."
        )
        return False
    return True


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
    # --- 0. Snap Chromium detection — fail fast with a clear message ---
    for snap_path in _SNAP_BROWSER_PATHS:
        if _binary_exists(snap_path):
            raise RuntimeError(
                "Snap Chromium detected but it CANNOT be used with Selenium.\n"
                "The snap sandbox prevents chromedriver from launching the browser.\n"
                "\n"
                "Fix — replace snap Chromium with the apt version:\n"
                "  sudo snap remove chromium\n"
                "  sudo apt update\n"
                "  sudo apt install -y chromium chromium-driver        # Ubuntu 22.04+\n"
                "  # OR for Ubuntu 20.04:\n"
                "  sudo apt install -y chromium-browser chromium-chromedriver\n"
                "\n"
                "Then restart the dashboard."
            )

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
                # Verify versions match before committing to this pair
                if _versions_match(browser, driver):
                    logger.info(f"Browser binary : {browser}")
                    logger.info(f"ChromeDriver   : {driver}")
                    ver = _get_version(browser)
                    if ver:
                        logger.info(f"Browser version: {ver}")
                    return browser, driver
                else:
                    # Version mismatch — skip system driver, use webdriver-manager
                    logger.info(f"Browser binary : {browser}")
                    ver = _get_version(browser)
                    if ver:
                        logger.info(f"Browser version: {ver}")
                    return browser, None
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
        self._tmp_dir: Optional[str] = None
        self._setup_driver()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _build_options(self) -> Options:
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")
            logger.info("Running in headless mode")

        # ----------------------------------------------------------------
        # Flags required for stable operation on headless servers / Docker
        # ----------------------------------------------------------------
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--window-size=1920,1080")

        # Fix "DevToolsActivePort file doesn't exist" on servers:
        # Use a dedicated temp directory for each Chrome instance so
        # multiple sessions don't collide, and disable the remote
        # debugging port that causes the crash.
        self._tmp_dir = tempfile.mkdtemp(prefix="chrome_tmp_")
        options.add_argument(f"--user-data-dir={self._tmp_dir}")
        options.add_argument("--remote-debugging-port=0")  # 0 = OS picks a free port

        # Additional stability flags for server environments
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-translate")
        options.add_argument("--metrics-recording-only")
        options.add_argument("--mute-audio")
        options.add_argument("--no-first-run")
        options.add_argument("--safebrowsing-disable-auto-update")
        options.add_argument("--single-process")   # helps in low-memory VPS environments

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
                # No matching system chromedriver — use webdriver-manager to download
                # the correct version for the installed browser.
                logger.info(
                    "No matching system chromedriver found — using webdriver-manager "
                    "to download the correct version. This requires internet access."
                )
                service = self._get_webdriver_manager_service(browser_bin)

            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Selenium WebDriver initialised successfully")

        except Exception as e:
            # Clean up the temp dir if Chrome failed to start
            if self._tmp_dir:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
                self._tmp_dir = None
            logger.error(
                f"WebDriver initialisation failed: {e}\n"
                "Troubleshooting:\n"
                "  1. Check browser version:   chromium-browser --version\n"
                "  2. Check driver version:    chromedriver --version\n"
                "  3. If versions mismatch, the bot will auto-download the correct driver\n"
                "     via webdriver-manager (requires internet access).\n"
                "  4. Or set 'Chromium Path' in the dashboard to your browser binary path."
            )
            raise

    @staticmethod
    def _get_webdriver_manager_service(browser_bin: Optional[str]) -> Service:
        """Download and return a Service using webdriver-manager."""
        try:
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            raise RuntimeError(
                "webdriver-manager is not installed. "
                "Run: pip install webdriver-manager"
            )

        # Use ChromeType.CHROMIUM when the browser is Chromium (not Google Chrome)
        is_chromium = browser_bin and (
            "chromium" in browser_bin.lower()
        )
        if is_chromium:
            try:
                from webdriver_manager.core.os_manager import ChromeType
                logger.info("Downloading chromedriver for Chromium via webdriver-manager...")
                return Service(
                    ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                )
            except Exception as e:
                logger.warning(f"ChromeType.CHROMIUM download failed ({e}), trying generic...")

        logger.info("Downloading chromedriver via webdriver-manager...")
        return Service(ChromeDriverManager().install())

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
        # Clean up the temporary user-data-dir to avoid disk accumulation
        if self._tmp_dir:
            try:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)
            except Exception:
                pass
            self._tmp_dir = None
