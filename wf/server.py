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
from wf.utils.validate import DrivePath, StaticAP, MobileTrack

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
        return JSONResponse(status_code=200,
                            content={"mission": request.app.state.mission})

    @app.get("/api/drive-path", response_model=list[DrivePath])
    async def get_drive_path(request: Request):
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        return dao.get_drive_path()
   
    @app.get("/api/static-ap", response_model=list[StaticAP])
    async def get_static_ap(request: Request):
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        return dao.get_static_ap()

    @app.get("/api/mobile-track", response_model=list[MobileTrack])
    async def get_mobile_track(request: Request):
        mission = request.app.state.mission
        dao = DAO(f"wf_{mission}.sqlite")
        return dao.get_mobile_tracks()

    # mount the static UI last
    static_dir = Path(__file__).parent / "webapp"
    if not static_dir.exists():
        logger.warning("Static directory %s does not exist", static_dir)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="webapp")


    return app