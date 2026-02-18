import random
import shutil
import subprocess
import time
from typing import Optional

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

# Candidate browser binary names to search for (in priority order)
_BROWSER_CANDIDATES = [
    "chromium-browser",
    "chromium",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
]

# Candidate chromedriver binary names to search for
_DRIVER_CANDIDATES = [
    "chromedriver",
    "chromium-chromedriver",
]


def _find_binary(candidates: list) -> Optional[str]:
    """Return the first candidate found on PATH, or None."""
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def _get_chromium_version(binary: str) -> Optional[str]:
    """Return the major version string of a Chrome/Chromium binary, or None."""
    try:
        out = subprocess.check_output(
            [binary, "--version"], stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        # e.g. "Chromium 124.0.6367.60 snap" or "Google Chrome 124.0.6367.60"
        parts = out.split()
        for part in parts:
            if part[0].isdigit():
                return part.split(".")[0]
    except Exception:
        pass
    return None


class SeleniumDriver:
    """Wrapper for Selenium WebDriver with Chromium/Chrome.

    Auto-detects the system Chromium/Chrome binary and its matching
    chromedriver so the bot works out-of-the-box on Ubuntu servers
    without needing webdriver-manager to download anything.
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

    def _resolve_browser_and_driver(self):
        """
        Return (browser_binary, chromedriver_binary).

        Priority:
        1. Explicit chromium_path from config (user-supplied)
        2. System Chromium/Chrome binary auto-detected via PATH
        3. webdriver-manager download (last resort, may fail on servers)
        """
        browser_bin = self.chromium_path or _find_binary(_BROWSER_CANDIDATES)
        driver_bin = _find_binary(_DRIVER_CANDIDATES)

        if browser_bin:
            logger.info(f"Browser binary: {browser_bin}")
            ver = _get_chromium_version(browser_bin)
            if ver:
                logger.info(f"Browser version: {ver}")
        else:
            logger.warning(
                "No Chrome/Chromium binary found on PATH. "
                "Install it with: sudo apt install -y chromium"
            )

        if driver_bin:
            logger.info(f"ChromeDriver: {driver_bin}")
        else:
            logger.warning(
                "No chromedriver found on PATH. "
                "Install it with: sudo apt install -y chromium-driver"
            )

        return browser_bin, driver_bin

    def _setup_driver(self):
        options = self._build_options()
        browser_bin, driver_bin = self._resolve_browser_and_driver()

        # Tell Selenium which browser binary to use
        if browser_bin:
            options.binary_location = browser_bin

        try:
            if driver_bin:
                # Use the system chromedriver — no download needed
                service = Service(driver_bin)
            else:
                # Fall back to webdriver-manager (requires internet access)
                logger.warning(
                    "Falling back to webdriver-manager to download chromedriver. "
                    "This requires internet access and may fail if versions mismatch."
                )
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    from webdriver_manager.core.os_manager import ChromeType
                    # Try Chromium-specific driver first
                    try:
                        service = Service(
                            ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
                        )
                    except Exception:
                        service = Service(ChromeDriverManager().install())
                except ImportError:
                    raise RuntimeError(
                        "chromedriver not found on PATH and webdriver-manager is not installed. "
                        "Run: sudo apt install -y chromium-driver"
                    )

            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Selenium WebDriver initialised successfully")

        except Exception as e:
            logger.error(
                f"Failed to initialise WebDriver: {e}\n"
                "Troubleshooting tips:\n"
                "  1. Install Chromium:   sudo apt install -y chromium chromium-driver\n"
                "  2. Or set 'chromium_path' in the dashboard / config file\n"
                "  3. Make sure headless mode is ON when running on a server"
            )
            raise

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def get(self, url: str):
        try:
            logger.debug(f"Navigating to: {url}")
            self.driver.get(url)
            # Brief pause to let the page start loading
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
