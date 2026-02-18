from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
import time
import random
from bot.logger import setup_logger

logger = setup_logger(__name__)

class SessionSimulator:
    """Simulate user engagement for Google Analytics"""
    
    def __init__(self, driver, session_duration=45):
        self.driver = driver
        self.session_duration = session_duration
    
    def simulate_engagement(self):
        try:
            logger.info(f"Simulating engagement for {self.session_duration} seconds")
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            time.sleep(random.uniform(2, 5))
            for _ in range(random.randint(2, 5)):
                scroll_amount = random.randint(100, min(500, total_height))
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                logger.debug(f"Scrolled {scroll_amount}px")
                time.sleep(random.uniform(1, 3))
            try:
                body = self.driver.find_element(By.TAG_NAME, "body")
                actions = ActionChains(self.driver)
                actions.move_to_element(body).perform()
            except:
                pass
            start_time = time.time()
            remaining = self.session_duration
            while remaining > 0:
                if random.random() > 0.7:
                    try:
                        self.driver.execute_script("window.scrollBy(0, 50);")
                    except:
                        pass
                time.sleep(random.uniform(2, 4))
                remaining = self.session_duration - (time.time() - start_time)
            logger.info("Engagement simulation completed")
        except Exception as e:
            logger.error(f"Error during engagement simulation: {e}")