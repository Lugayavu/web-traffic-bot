import threading
import time
from concurrent.futures import ThreadPoolExecutor

from bot.logger import setup_logger
from bot.proxy_manager import ProxyManager
from bot.selenium_driver import SeleniumDriver, resolve_driver_once
from bot.session_simulator import SessionSimulator

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level stop flag.
# The dashboard sets this to True to request a graceful shutdown.
# TrafficBot.run() resets it to False at the start of each run.
# ---------------------------------------------------------------------------
_STOP_REQUESTED: bool = False

# Thread-safe counters lock
_counter_lock = threading.Lock()


def request_stop() -> None:
    """Ask the currently-running bot to stop after the current session."""
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


class TrafficBot:
    """
    Main traffic bot orchestrator.

    Supports multiple target URLs — sessions are distributed round-robin
    across all configured URLs. Per-URL stats are tracked separately.

    Supports concurrent sessions: up to `concurrent_sessions` browser
    windows run simultaneously. As each one finishes, a new one starts
    immediately so the concurrency level is always maintained.
    """

    def __init__(self, config):
        self.config = config
        self.proxy_manager = ProxyManager(config.proxies)

        # Global counters
        self.sessions_completed = 0
        self.sessions_failed = 0

        # Per-URL counters: {url: {"completed": int, "failed": int}}
        self.url_stats: dict = {
            url: {"completed": 0, "failed": 0}
            for url in config.target_urls
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        global _STOP_REQUESTED
        _STOP_REQUESTED = False  # reset on each run

        urls = self.config.target_urls
        concurrency = max(1, self.config.concurrent_sessions)

        logger.info("=" * 60)
        logger.info("WEB TRAFFIC BOT STARTED")
        logger.info("=" * 60)
        logger.info(f"Target URLs         : {len(urls)}")
        for i, url in enumerate(urls, 1):
            logger.info(f"  {i}. {url}")
        logger.info(f"Total Sessions      : {self.config.sessions_count}")
        logger.info(f"Concurrent Sessions : {concurrency}")
        logger.info(f"Session Duration    : {self.config.session_duration}s")
        logger.info(f"Total Duration      : {self.config.duration_seconds}s")
        logger.info(f"Proxies             : {len(self.config.proxies)}")
        logger.info(f"Headless            : {self.config.headless}")
        logger.info("=" * 60)

        # Pre-resolve chromedriver ONCE before the thread pool starts
        pre_driver_path = resolve_driver_once(self.config.chromium_path)
        if pre_driver_path:
            logger.info(f"ChromeDriver pre-resolved: {pre_driver_path}")

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {}
            session_num = 0

            while session_num < self.config.sessions_count:
                if time.time() - start_time > self.config.duration_seconds:
                    logger.info(f"Total duration reached ({self.config.duration_seconds}s). Stopping.")
                    break

                if _STOP_REQUESTED:
                    logger.info("Stop requested. No more sessions will be started.")
                    break

                while (len(futures) < concurrency
                       and session_num < self.config.sessions_count
                       and not _STOP_REQUESTED):
                    session_num += 1
                    # Round-robin URL assignment
                    url = urls[(session_num - 1) % len(urls)]
                    future = pool.submit(self._run_session, session_num, url, pre_driver_path)
                    futures[future] = (session_num, url)
                    logger.info(
                        f"[Session {session_num}/{self.config.sessions_count}] "
                        f"→ {url}  (active: {len(futures)})"
                    )

                if futures:
                    done_futures = [f for f in list(futures.keys()) if f.done()]
                    if not done_futures:
                        time.sleep(0.5)
                        continue

                    for f in done_futures:
                        snum, url = futures.pop(f)
                        try:
                            f.result()
                            with _counter_lock:
                                self.sessions_completed += 1
                                self.url_stats[url]["completed"] += 1
                            logger.info(f"[Session {snum}] ✓ {url}")
                        except Exception as e:
                            with _counter_lock:
                                self.sessions_failed += 1
                                self.url_stats[url]["failed"] += 1
                            logger.error(f"[Session {snum}] ✗ {url}: {e}")

            # Wait for remaining in-flight sessions
            logger.info("Waiting for in-flight sessions to finish...")
            for f, (snum, url) in list(futures.items()):
                try:
                    f.result()
                    with _counter_lock:
                        self.sessions_completed += 1
                        self.url_stats[url]["completed"] += 1
                    logger.info(f"[Session {snum}] ✓ {url}")
                except Exception as e:
                    with _counter_lock:
                        self.sessions_failed += 1
                        self.url_stats[url]["failed"] += 1
                    logger.error(f"[Session {snum}] ✗ {url}: {e}")

        self._print_summary(time.time() - start_time)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_session(self, session_num: int, url: str, pre_driver_path=None):
        """Run a single browser session for the given URL."""
        driver = None
        try:
            proxy = self.proxy_manager.get_next_proxy()
            if proxy:
                logger.info(f"[Session {session_num}] Using proxy: {proxy}")

            driver = SeleniumDriver(
                headless=self.config.headless,
                proxy=proxy,
                chromium_path=self.config.chromium_path,
                driver_path=pre_driver_path,
            )
            driver.get(url)

            simulator = SessionSimulator(driver.driver, self.config.session_duration)
            simulator.simulate_engagement()

        finally:
            if driver:
                driver.quit()

    def _print_summary(self, duration: float):
        total = self.sessions_completed + self.sessions_failed
        logger.info("\n" + "=" * 60)
        logger.info("EXECUTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Sessions Completed : {self.sessions_completed}")
        logger.info(f"Sessions Failed    : {self.sessions_failed}")
        logger.info(f"Total Duration     : {duration:.2f}s ({duration / 60:.2f}m)")
        if total > 0:
            logger.info(f"Success Rate       : {self.sessions_completed / total * 100:.1f}%")
        logger.info("")
        logger.info("Per-URL breakdown:")
        for url, stats in self.url_stats.items():
            url_total = stats["completed"] + stats["failed"]
            rate = f"{stats['completed'] / url_total * 100:.0f}%" if url_total else "—"
            logger.info(f"  {url}")
            logger.info(f"    Completed: {stats['completed']}  Failed: {stats['failed']}  Rate: {rate}")
        logger.info("=" * 60)
