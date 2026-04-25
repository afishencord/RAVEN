from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_admin
from app.models import Node, NodeGroup, User
from app.schemas import NodeGroupCreate, NodeGroupRead
from app.services.incident_workflow import write_audit_log

router = APIRouter(prefix="/node-groups", tags=["node-groups"])


def _normalized_name(name: str) -> str:
    return " ".join(name.strip().split())


@router.get("", response_model=list[NodeGroupRead])
def list_node_groups(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(NodeGroup).order_by(NodeGroup.name.asc()).all()


@router.post("", response_model=NodeGroupRead, status_code=status.HTTP_201_CREATED)
def create_node_group(payload: NodeGroupCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    name = _normalized_name(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")
    existing = db.query(NodeGroup).filter(NodeGroup.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Folder already exists")
    group = NodeGroup(name=name)
    db.add(group)
    db.commit()
    db.refresh(group)
    write_audit_log(db, actor=current_user, entity_type="node_group", entity_id=str(group.id), action="created", details={"name": name})
    db.commit()
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node_group(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    group = db.query(NodeGroup).filter(NodeGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Folder not found")
    db.query(Node).filter(Node.group_name == group.name).update({Node.group_name: None})
    db.delete(group)
    write_audit_log(db, actor=current_user, entity_type="node_group", entity_id=str(group_id), action="deleted", details={"name": group.name})
    db.commit()
