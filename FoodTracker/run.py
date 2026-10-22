"""Start FoodShare Tracker.

    python run.py                                   this computer only (http://localhost:8501)
    python run.py --network --cert C.pem --key K.pem   phones and other computers too, over HTTPS
    python run.py --demo                            isolated classroom demonstration

Press Ctrl+C to stop. Demo data is created only with --demo or FOODSHARE_DEMO=1.
"""

import argparse
import os
import socket
import sys

if sys.version_info < (3, 11):
    sys.exit("FoodShare Tracker needs Python 3.11 or newer.")

from streamlit.web import cli  # noqa: E402

from foodshare import APP_DIR, data_path  # noqa: E402


def _local_address():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))  # no data is sent
            return probe.getsockname()[0]
    except OSError:
        return "this-computer's-address"


def main():
    parser = argparse.ArgumentParser(description="Start FoodShare Tracker.")
    parser.add_argument("--demo", action="store_true", help="use an isolated demonstration database")
    parser.add_argument("--network", action="store_true",
                        help="let phones and other computers on the network open the app")
    parser.add_argument("--cert", help="HTTPS certificate file (.pem)")
    parser.add_argument("--key", help="HTTPS private key file (.pem)")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error("--cert and --key go together.")

    if args.cert:
        args.cert, args.key = os.path.abspath(args.cert), os.path.abspath(args.key)
    os.chdir(APP_DIR)  # so Streamlit reads .streamlit/config.toml
    if args.network and not args.cert:
        parser.error("Network access requires --cert and --key for HTTPS.")
    from foodshare import domain as d
    if args.demo:
        os.environ["FOODSHARE_DEMO"] = "1"
    if d.demo_mode() and "FOODSHARE_DB" not in os.environ:
        os.environ["FOODSHARE_DB"] = os.path.join(APP_DIR, "data", "demo.sqlite3")
    if d.demo_mode() and not os.path.exists(data_path()):
        from seed import DEMO_PASSWORD, seed
        seed(data_path())
        print(f"Created demo data. Every demo password is: {DEMO_PASSWORD}")

    from foodshare.storage import SqliteStore
    from foodshare.services import run_maintenance
    run_maintenance(SqliteStore(data_path()))
    import streamlit as st
    from foodshare.http_security import routes
    os.environ["FOODSHARE_COOKIE_ENDPOINT"] = "1"
    config = {"server.port": args.port, "server.address": "0.0.0.0" if args.network else "localhost",
              "server.headless": True, "global.developmentMode": False, "server.enableXsrfProtection": True,
              "server.enableCORS": True, "browser.gatherUsageStats": False}
    if args.cert:
        config.update({"server.sslCertFile": args.cert, "server.sslKeyFile": args.key})
    if args.network:
        config["browser.serverAddress"] = _local_address()
        scheme = "https" if args.cert else "http"
        print(f"Open {scheme}://{_local_address()}:{args.port}")
    st.App(os.path.join(APP_DIR, "app.py"), routes=routes()).run(config=config)


if __name__ == "__main__":
    main()
