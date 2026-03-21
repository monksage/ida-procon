"""
ida-procon-api: coordinator daemon for agent-driven reverse engineering.

Usage:
    python main.py --dump-dir D:/desktop/frida/big_question/dump --port 13340
"""

import sys
from pathlib import Path

# add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from fastapi import FastAPI

from config import parse_args
from services.registry import Registry
from services.claimer import Claimer
from services.resolver import Resolver
from services.contour_builder import ContourBuilder
from services.write_queue import WriteQueue
from api import routes_query, routes_mutate


def create_app(dump_dir: Path, claim_ttl: int = 600) -> FastAPI:
    app = FastAPI(title="ida-procon-api", version="0.1.0")

    # init services
    print("Loading modules...")
    registry = Registry(dump_dir)
    claimer = Claimer(ttl=claim_ttl)
    write_queue = WriteQueue()
    resolver = Resolver(registry, write_queue)
    contour_builder = ContourBuilder(registry, write_queue)

    # start write queue worker
    write_queue.start(registry)

    # inject dependencies into routes
    routes_query.init(registry, claimer)
    routes_mutate.init(registry, claimer, resolver, contour_builder)

    # register routers
    app.include_router(routes_query.router)
    app.include_router(routes_mutate.router)

    @app.on_event("shutdown")
    def shutdown():
        write_queue.stop()

    print(f"Ready. Modules: {registry.list_modules()}")
    return app


def main():
    cfg = parse_args()
    app = create_app(cfg.dump_dir, cfg.claim_ttl)
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
