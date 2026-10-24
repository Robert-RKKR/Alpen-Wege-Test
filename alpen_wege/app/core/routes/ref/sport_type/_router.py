# Third-party
from fastapi import APIRouter

# Special: SportType (name required)
router = APIRouter(prefix="/sport-types", tags=["Reference - Sport Types"])
