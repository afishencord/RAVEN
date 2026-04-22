from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import RemediationProfile, User
from app.schemas import RemediationProfileRead

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=list[RemediationProfileRead])
def list_profiles(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(RemediationProfile).order_by(RemediationProfile.name.asc()).all()
