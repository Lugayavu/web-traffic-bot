import time
from bot.logger import setup_logger
from bot.selenium_driver import SeleniumDriver
from bot.proxy_manager import ProxyManager
from bot.session_simulator import SessionSimulator

logger = setup_logger(__name__)

class TrafficBot:
    """Main traffic bot orchestrator"""
    
    def __init__(self, config):
        self.config = config
        self.proxy_manager = ProxyManager(config.proxies)
        self.sessions_completed = 0
        self.sessions_failed = 0
    
    def run(self):
        logger.info("=" * 60)
        logger.info("WEB TRAFFIC BOT STARTED")
        logger.info("=" * 60)
        logger.info(f"Target URL: {self.config.target_url}")
        logger.info(f"Total Sessions: {self.config.sessions_count}")
        logger.info(f"Session Duration: {self.config.session_duration}s")
        logger.info(f"Total Duration: {self.config.duration_seconds}s")
        logger.info(f"Proxies Available: {len(self.config.proxies)}")
        logger.info("=" * 60)
        start_time = time.time()
        for session_num in range(1, self.config.sessions_count + 1):
            elapsed = time.time() - start_time
            if elapsed > self.config.duration_seconds:
                logger.info(f"Total duration reached ({self.config.duration_seconds}s). Stopping.")
                break
            try:
                logger.info(f"\n[Session {session_num}/{self.config.sessions_count}]")
                self._run_session(session_num)
                self.sessions_completed += 1
            except Exception as e:
                logger.error(f"Session {session_num} failed: {e}")
                self.sessions_failed += 1
            if session_num < self.config.sessions_count:
                time.sleep(2)
        self._print_summary(time.time() - start_time)
    
    def _run_session(self, session_num):
        driver = None
        try:
            proxy = self.proxy_manager.get_next_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy}")
            driver = SeleniumDriver(
                headless=self.config.headless,
                proxy=proxy,
                chromium_path=self.config.chromium_path
            )
            driver.get(self.config.target_url)
            simulator = SessionSimulator(driver.driver, self.config.session_duration)
            simulator.simulate_engagement()
            logger.info(f"Session {session_num} completed successfully")
        finally:
            if driver:
                driver.quit()
    
    def _print_summary(self, duration):
        logger.info("\n" + "=" * 60)
        logger.info("EXECUTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Sessions Completed: {self.sessions_completed}")
        logger.info(f"Sessions Failed: {self.sessions_failed}")
        logger.info(f"Total Duration: {duration:.2f}s ({duration/60:.2f}m)")
        if self.sessions_completed + self.sessions_failed > 0:
            logger.info(f"Success Rate: {(self.sessions_completed / (self.sessions_completed + self.sessions_failed) * 100):.1f}%")
        logger.info("=" * 60)