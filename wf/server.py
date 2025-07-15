# wf/server.py
"""
FastAPI server for the wf CLI.
"""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse

from wf.utils.log import get_logger
from wf.storage.dao import DAO
from wf.utils.validate import DrivePath, StaticAP, MobileTrack, UIFilter

logger = get_logger(__name__)


def create_app(mission: str) -> FastAPI:
    """
    Build a FastAPI instance bound to a specific mission.
    """
    app = FastAPI()
    app.state.mission = mission

    # mount all API endpoints first
    @app.get("/api/status", response_class=JSONResponse)
    async def status() -> JSONResponse:
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.get("/api/mission", response_class=JSONResponse)
    async def get_mission(request: Request) -> JSONResponse:
        return JSONResponse(status_code=200, content={"mission": request.app.state.mission})

    @app.get("/api/max-packets", response_class=JSONResponse)
    async def get_max_packets(request: Request) -> JSONResponse:
        """
        return min and max packet counts across static aps and mobile tracks.
        """
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        max_packets = dao.get_max_packets()
        return JSONResponse(
            status_code=200, 
            content={"max_packets": max_packets}
        )
    
    @app.get("/api/max-points", response_class=JSONResponse)
    async def get_max_points(request: Request) -> JSONResponse:
        """
        return min and max number of points per mobile track.
        """
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        max_pts = dao.get_max_mobile_points()
        return JSONResponse(
            status_code=200, 
            content={"max_points": max_pts}
        )

    @app.get("/api/time-range", response_class=JSONResponse)
    async def get_time_range(request: Request) -> JSONResponse:
        """
        return min and max timestamps across sessions.
        """
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        min_ts, max_ts = dao.get_time_range()
        return JSONResponse(
            status_code=200, 
            content={
                "min_ts": min_ts,
                "max_ts": max_ts
        })

    @app.post("/api/drive-path", response_model=list[DrivePath])
    async def get_drive_path(request: Request, filter: UIFilter):
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        return dao.get_drive_path(filter)

    @app.post("/api/static-ap", response_model=list[StaticAP])
    async def get_static_ap(request: Request, filter: UIFilter):
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        return dao.get_static_ap(filter)

    @app.post("/api/mobile-track", response_model=list[MobileTrack])
    async def get_mobile_track(request: Request, filter: UIFilter):
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        return dao.get_mobile_tracks(filter)

    @app.post("/api/atmos", response_class=JSONResponse)
    async def get_atmos(request: Request, filter: UIFilter):
        """
        Return summary statistics based on the UI filter
        """
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        enc = dao.get_encryption_counts(filter)
        mac = dao.get_mac_counts(filter)
        unique_macs = dao.get_unique_mac_count(filter)
        unique_ssids = dao.get_unique_ssid_count(filter)
        oui = dao.get_oui_counts(filter)
        return JSONResponse(
            status_code=200,
            content={
                "encryption_counts": enc,
                "oui_counts": oui,
                "unique_mac_count": unique_macs,
                "unique_ssid_count": unique_ssids,
                "mac_counts": mac,
            },
        )

    # mount the static UI last
    static_dir = Path(__file__).parent / "webapp"
    if not static_dir.exists():
        logger.warning("Static directory %s does not exist", static_dir)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="webapp")

    return app
