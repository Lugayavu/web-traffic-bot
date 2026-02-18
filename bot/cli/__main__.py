import argparse
import sys
from bot.config_handler import ConfigHandler
from bot.traffic_bot import TrafficBot
from bot.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Web Traffic Bot - Load testing and traffic simulation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  web-traffic-bot --url https://example.com --sessions 50 --duration 3600
  web-traffic-bot --config config.yaml
  web-traffic-bot --config config.yaml --url https://example.com --sessions 10
        """
    )
    parser.add_argument(
        '--url', '--target-url',
        dest='url',
        help='Target URL to test'
    )
    parser.add_argument(
        '--config', '-c',
        help='Path to YAML config file'
    )
    parser.add_argument(
        '--sessions',
        type=int,
        help='Number of sessions to run'
    )
    parser.add_argument(
        '--duration',
        type=int,
        help='Total duration in seconds'
    )
    parser.add_argument(
        '--session-duration',
        type=int,
        dest='session_duration',
        help='Duration per session in seconds'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        default=True,
        help='Run in headless mode (default: True)'
    )
    parser.add_argument(
        '--no-headless',
        action='store_false',
        dest='headless',
        help='Run with visible browser'
    )
    parser.add_argument(
        '--proxy',
        action='append',
        dest='proxies',
        metavar='PROXY_URL',
        help='Proxy URL (can be repeated for multiple proxies)'
    )

    args = parser.parse_args()

    try:
        # Build config - file is optional; CLI flags override file values
        config = ConfigHandler(args.config)

        if args.url:
            config.target_url = args.url
        if args.sessions:
            config.sessions_count = args.sessions
        if args.duration:
            config.duration_seconds = args.duration
        if args.session_duration:
            config.session_duration = args.session_duration
        if args.headless is not None:
            config.headless = args.headless
        if args.proxies:
            config.proxies = args.proxies

        # Validate after all overrides are applied
        config.validate()

        bot = TrafficBot(config)
        bot.run()

    except (ValueError, FileNotFoundError) as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
