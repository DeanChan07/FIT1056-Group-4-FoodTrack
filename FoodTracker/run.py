"""Start FoodShare Tracker.

    python run.py                                   this computer only (http://localhost:8501)
    python run.py --network --cert C.pem --key K.pem   phones and other computers too, over HTTPS
    python run.py --network                         same, without HTTPS (trusted test network only)

Press Ctrl+C in this window to stop it. Demo data is created the first time.
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
    parser.add_argument("--network", action="store_true",
                        help="let phones and other computers on the network open the app")
    parser.add_argument("--cert", help="HTTPS certificate file (.pem)")
    parser.add_argument("--key", help="HTTPS private key file (.pem)")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    if bool(args.cert) != bool(args.key):
        parser.error("--cert and --key go together.")

    os.chdir(APP_DIR)  # so Streamlit reads .streamlit/config.toml
    if not os.path.exists(data_path()):
        from seed import DEMO_PASSWORD, seed
        seed(data_path())
        print(f"Created demo data. Every demo password is: {DEMO_PASSWORD}")

    options = ["--server.port", str(args.port)]
    scheme = "https" if args.cert else "http"
    if args.cert:
        options += ["--server.sslCertFile", args.cert, "--server.sslKeyFile", args.key]
    if args.network:
        host = _local_address()
        options += ["--server.address", "0.0.0.0", "--browser.serverAddress", host,
                    "--server.headless", "true"]
        print(f"\nOther devices on this network can open: {scheme}://{host}:{args.port}")
        if not args.cert:
            print("WARNING: without --cert and --key, passwords and needs details travel "
                  "unencrypted.\nOnly do this on a network you trust, for testing.\n")
    sys.argv = ["streamlit", "run", os.path.join(APP_DIR, "app.py")] + options
    sys.exit(cli.main())


if __name__ == "__main__":
    main()
