import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mig_lib import *
R = f"{APP}/compendium/routes"
make_folder_resource(
    f"{R}/poi.py", f"{R}/poi", 'router = APIRouter(prefix="/pois", tags=["Compendium - POI"])',
    endpoints={
        "upload_csv": ["upload_csv"], "rescan": ["rescan_poi"], "get_many": ["list_pois"], "create": ["create_poi"],
        "get_one": ["get_poi"], "update": ["update_poi"], "delete": ["delete_poi"],
    },
    shared=["_EAGER", "_apply_scope"], shared_rename={"_EAGER": "EAGER", "_apply_scope": "apply_scope"},
)
make_folder_resource(
    f"{R}/card.py", f"{R}/card", 'router = APIRouter(prefix="/cards", tags=["Compendium - Card"])',
    endpoints={
        "upload_csv": ["upload_csv"], "rescan": ["rescan_card"], "get_many": ["list_cards"], "create": ["create_card"],
        "get_one": ["get_card"], "update": ["update_card"], "delete": ["delete_card"],
    },
    shared=["_EAGER", "_apply_scope"], shared_rename={"_EAGER": "EAGER", "_apply_scope": "apply_scope"},
)
# compendium/routes/__init__.py keeps working: `from .poi import router as poi_router`

R2 = f"{APP}/explorer/routes"
make_folder_resource(
    f"{R2}/track.py", f"{R2}/track", 'router = APIRouter(prefix="/tracks", tags=["Explorer - Track"])',
    endpoints={
        "create": ["create_track"], "get_many": ["list_tracks"], "get_one": ["get_track"],
        "geometry": ["get_track_geometry"], "performance": ["get_track_performance"], "update": ["update_track"],
        "archive": ["archive_track"], "restore": ["restore_track"], "reprocess": ["reprocess_track"],
    },
    shared=["_apply_scope", "_apply_visibility", "_ensure_visible", "_build_metrics"],
    shared_rename={"_apply_scope": "apply_scope", "_apply_visibility": "apply_visibility",
                   "_ensure_visible": "ensure_visible", "_build_metrics": "build_metrics"},
    module_vars={"logger": "logger = logging.getLogger(__name__)", "settings": "settings = get_settings()"},
)
