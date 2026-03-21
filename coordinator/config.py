import argparse
from pathlib import Path


class Config:
    dump_dir: Path
    host: str
    port: int
    claim_ttl: int  # seconds before unclaimed claims expire

    def __init__(self, dump_dir: Path, host: str = "127.0.0.1",
                 port: int = 40000, claim_ttl: int = 600):
        self.dump_dir = dump_dir
        self.host = host
        self.port = port
        self.claim_ttl = claim_ttl


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="ida-procon-api coordinator daemon")
    parser.add_argument(
        "--dump-dir",
        type=Path,
        default=Path("D:/desktop/frida/big_question/dump"),
        help="Path to dump directory containing module folders",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=40000)
    parser.add_argument("--claim-ttl", type=int, default=600,
                        help="Seconds before an unclaimed entry expires")
    args = parser.parse_args()
    return Config(
        dump_dir=args.dump_dir,
        host=args.host,
        port=args.port,
        claim_ttl=args.claim_ttl,
    )
