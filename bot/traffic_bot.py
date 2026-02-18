import time

from bot.logger import setup_logger
from bot.proxy_manager import ProxyManager
from bot.selenium_driver import SeleniumDriver
from bot.session_simulator import SessionSimulator

logger = setup_logger(__name__)

# Set to True from the dashboard to request a graceful stop
_STOP_REQUESTED: bool = False


class TrafficBot:
    """Main traffic bot orchestrator."""

    def __init__(self, config):
        self.config = config
        self.proxy_manager = ProxyManager(config.proxies)
        self.sessions_completed = 0
        self.sessions_failed = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        import bot.traffic_bot as _self_module
        _self_module._STOP_REQUESTED = False  # reset on each run

        logger.info("=" * 60)
        logger.info("WEB TRAFFIC BOT STARTED")
        logger.info("=" * 60)
        logger.info(f"Target URL      : {self.config.target_url}")
        logger.info(f"Total Sessions  : {self.config.sessions_count}")
        logger.info(f"Session Duration: {self.config.session_duration}s")
        logger.info(f"Total Duration  : {self.config.duration_seconds}s")
        logger.info(f"Proxies         : {len(self.config.proxies)}")
        logger.info(f"Headless        : {self.config.headless}")
        logger.info("=" * 60)

        start_time = time.time()

        for session_num in range(1, self.config.sessions_count + 1):
            # Check hard time limit
            elapsed = time.time() - start_time
            if elapsed > self.config.duration_seconds:
                logger.info(f"Total duration reached ({self.config.duration_seconds}s). Stopping.")
                break

            # Check dashboard stop request
            if _self_module._STOP_REQUESTED:
                logger.info("Stop requested via dashboard. Stopping after current session.")
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_session(self, session_num):
        driver = None
        try:
            proxy = self.proxy_manager.get_next_proxy()
            if proxy:
                logger.info(f"Using proxy: {proxy}")

            driver = SeleniumDriver(
                headless=self.config.headless,
                proxy=proxy,
                chromium_path=self.config.chromium_path,
            )
            driver.get(self.config.target_url)

            simulator = SessionSimulator(driver.driver, self.config.session_duration)
            simulator.simulate_engagement()

            logger.info(f"Session {session_num} completed successfully")
        finally:
            if driver:
                driver.quit()

    def _print_summary(self, duration):
        total = self.sessions_completed + self.sessions_failed
        logger.info("\n" + "=" * 60)
        logger.info("EXECUTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Sessions Completed : {self.sessions_completed}")
        logger.info(f"Sessions Failed    : {self.sessions_failed}")
        logger.info(f"Total Duration     : {duration:.2f}s ({duration / 60:.2f}m)")
        if total > 0:
            logger.info(f"Success Rate       : {self.sessions_completed / total * 100:.1f}%")
        logger.info("=" * 60)
