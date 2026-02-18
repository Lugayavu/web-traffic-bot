import random
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

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


class SeleniumDriver:
    """Wrapper for Selenium WebDriver with Chromium/Chrome."""

    def __init__(self, headless=True, proxy=None, chromium_path=None):
        self.headless = headless
        self.proxy = proxy
        self.chromium_path = chromium_path
        self.driver = None
        self._setup_driver()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_driver(self):
        try:
            options = Options()

            if self.headless:
                # Modern headless flag (Chrome ≥ 112)
                options.add_argument("--headless=new")
                logger.info("Running in headless mode")

            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--window-size=1920,1080")

            # Rotate user-agent to look more natural
            ua = random.choice(USER_AGENTS)
            options.add_argument(f"--user-agent={ua}")
            logger.debug(f"User-agent: {ua}")

            if self.proxy:
                logger.info(f"Setting proxy: {self.proxy}")
                options.add_argument(f"--proxy-server={self.proxy}")

            if self.chromium_path:
                service = Service(self.chromium_path)
                logger.info(f"Using custom Chromium binary: {self.chromium_path}")
            else:
                service = Service(ChromeDriverManager().install())

            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Selenium WebDriver initialised successfully")

        except Exception as e:
            logger.error(f"Failed to initialise WebDriver: {e}")
            raise

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def get(self, url):
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
