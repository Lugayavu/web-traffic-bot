from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bot.logger import setup_logger
import time

logger = setup_logger(__name__)

class SeleniumDriver:
    """Wrapper for Selenium WebDriver with Chromium"""
    
    def __init__(self, headless=True, proxy=None, chromium_path=None):
        self.headless = headless
        self.proxy = proxy
        self.chromium_path = chromium_path
        self.driver = None
        self._setup_driver()
    
    def _setup_driver(self):
        try:
            options = Options()
            if self.headless:
                options.add_argument("--headless")
                logger.info("Running in headless mode")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            if self.proxy:
                logger.info(f"Setting proxy: {self.proxy}")
                options.add_argument(f"--proxy-server={self.proxy}")
            service = None
            if self.chromium_path:
                service = Service(self.chromium_path)
                logger.info(f"Using custom Chromium: {self.chromium_path}")
            else:
                service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            logger.info("Selenium WebDriver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise
    
    def get(self, url):
        try:
            logger.debug(f"Navigating to: {url}")
            self.driver.get(url)
            time.sleep(2)
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            raise
    
    def quit(self):
        if self.driver:
            self.driver.quit()
            logger.debug("WebDriver closed")