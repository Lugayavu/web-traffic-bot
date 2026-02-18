import random
import time

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from bot.logger import setup_logger

logger = setup_logger(__name__)


class SessionSimulator:
    """Simulate realistic user engagement for a single browser session."""

    def __init__(self, driver, session_duration=45):
        """
        Args:
            driver: Raw Selenium WebDriver instance.
            session_duration: How long (seconds) to keep the session alive.
        """
        self.driver = driver
        self.session_duration = session_duration

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate_engagement(self):
        """Run the full engagement simulation for this session."""
        try:
            logger.info(f"Simulating engagement for {self.session_duration}s")

            # Initial read pause
            time.sleep(random.uniform(2, 5))

            # Scroll through the page a few times
            self._scroll_page()

            # Move the mouse around to trigger hover events
            self._move_mouse()

            # Stay on the page for the remainder of the session duration
            self._idle_loop()

            logger.info("Engagement simulation completed")

        except WebDriverException as e:
            logger.error(f"WebDriver error during engagement simulation: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during engagement simulation: {e}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _scroll_page(self):
        """Scroll down the page in several random steps."""
        try:
            total_height = self.driver.execute_script(
                "return document.body.scrollHeight"
            )
            scroll_steps = random.randint(3, 7)
            for _ in range(scroll_steps):
                scroll_amount = random.randint(100, max(101, min(600, total_height // 4)))
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                logger.debug(f"Scrolled {scroll_amount}px")
                time.sleep(random.uniform(0.8, 2.5))

            # Occasionally scroll back up a bit (like a real reader)
            if random.random() > 0.5:
                self.driver.execute_script(
                    f"window.scrollBy(0, -{random.randint(100, 300)});"
                )
                time.sleep(random.uniform(0.5, 1.5))

        except WebDriverException as e:
            logger.debug(f"Scroll step skipped: {e}")

    def _move_mouse(self):
        """Move the mouse to the page body to trigger hover events."""
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            actions = ActionChains(self.driver)
            actions.move_to_element(body).perform()
        except WebDriverException as e:
            logger.debug(f"Mouse move skipped: {e}")

    def _idle_loop(self):
        """Keep the session alive with occasional micro-scrolls."""
        start_time = time.time()
        while True:
            elapsed = time.time() - start_time
            if elapsed >= self.session_duration:
                break
            # Occasionally do a tiny scroll to simulate reading
            if random.random() > 0.6:
                try:
                    self.driver.execute_script("window.scrollBy(0, 30);")
                except WebDriverException:
                    pass
            time.sleep(random.uniform(2, 4))
