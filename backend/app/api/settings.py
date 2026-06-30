from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_admin
from app.models import AppSetting, AuditLog, User
from app.schemas import PlatformSettingsBase, PlatformSettingsRead, PlatformSettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])

PLATFORM_SETTINGS_KEY = "platform"
DEFAULT_PLATFORM_SETTINGS = PlatformSettingsBase().model_dump()


def _settings_payload(row: AppSetting | None) -> dict:
    stored = row.value_json if row and isinstance(row.value_json, dict) else {}
    return {**DEFAULT_PLATFORM_SETTINGS, **{key: value for key, value in stored.items() if key in DEFAULT_PLATFORM_SETTINGS}}


@router.get("", response_model=PlatformSettingsRead)
def get_platform_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = db.query(AppSetting).filter(AppSetting.key == PLATFORM_SETTINGS_KEY).first()
    payload = _settings_payload(row)
    return PlatformSettingsRead(**payload, updated_at=row.updated_at if row else None)


@router.put("", response_model=PlatformSettingsRead)
def update_platform_settings(
    payload: PlatformSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = db.query(AppSetting).filter(AppSetting.key == PLATFORM_SETTINGS_KEY).first()
    if not row:
        row = AppSetting(key=PLATFORM_SETTINGS_KEY, value_json={})
        db.add(row)
        db.flush()

    next_payload = {**_settings_payload(row), **payload.model_dump(exclude_unset=True)}
    row.value_json = next_payload
    db.add(AuditLog(
        actor_user_id=current_user.id,
        entity_type="settings",
        entity_id=PLATFORM_SETTINGS_KEY,
        action="updated",
        details_json={"keys": sorted(payload.model_dump(exclude_unset=True).keys())},
    ))
    db.commit()
    db.refresh(row)
    return PlatformSettingsRead(**_settings_payload(row), updated_at=row.updated_at)
