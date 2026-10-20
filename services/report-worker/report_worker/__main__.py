"""`python -m report_worker`. 지금은 heartbeat만 돈다.

큐 소비자는 worker 트랙이 같은 루프에 붙인다.
"""

import asyncio
import logging

from report_worker import heartbeat


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("report_worker").info("heartbeat at %s", heartbeat.heartbeat_path())
    await heartbeat.run()


if __name__ == "__main__":
    asyncio.run(main())
