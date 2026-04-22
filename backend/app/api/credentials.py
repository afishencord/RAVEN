from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_db, require_admin
from app.models import Credential, User
from app.schemas import CredentialCreate, CredentialRead, CredentialUpdate

router = APIRouter(prefix="/credentials", tags=["credentials"])


def _serialize_credential(credential: Credential) -> CredentialRead:
    masked = "*" * 8 if credential.secret_value else ""
    return CredentialRead(
        id=credential.id,
        name=credential.name,
        kind=credential.kind,
        username=credential.username,
        description=credential.description,
        metadata_json=credential.metadata_json,
        has_secret=bool(credential.secret_value),
        masked_secret=masked,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.get("", response_model=list[CredentialRead])
def list_credentials(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    items = db.query(Credential).order_by(Credential.name.asc()).all()
    return [_serialize_credential(item) for item in items]


@router.post("", response_model=CredentialRead, status_code=status.HTTP_201_CREATED)
def create_credential(payload: CredentialCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    credential = Credential(**payload.model_dump())
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return _serialize_credential(credential)


@router.put("/{credential_id}", response_model=CredentialRead)
def update_credential(
    credential_id: int,
    payload: CredentialUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    credential = db.query(Credential).filter(Credential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(credential, key, value)
    db.commit()
    db.refresh(credential)
    return _serialize_credential(credential)


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(credential_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    credential = db.query(Credential).filter(Credential.id == credential_id).first()
    if not credential:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.delete(credential)
    db.commit()
