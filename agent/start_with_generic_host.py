import logging

from agent import HotelServicingBridgeAgent
from host_agent_server import create_and_run_host


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    create_and_run_host(HotelServicingBridgeAgent)


if __name__ == "__main__":
    main()
