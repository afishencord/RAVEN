from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_admin, require_operator_or_admin
from app.models import (
    ExecutionTask,
    Node,
    NodeAutomationEdge,
    NodeRemediationAssignment,
    NodeValidationAssignment,
    RemediationDefinition,
    User,
    ValidationDefinition,
    ValidationRun,
)
from app.schemas import (
    NodeAutomationEdgeRead,
    NodeAutomationAssignmentsRead,
    NodeAutomationAssignmentsUpdate,
    NodeRemediationAssignmentRead,
    NodeValidationAssignmentRead,
    RemediationDefinitionCreate,
    RemediationDefinitionRead,
    RemediationDefinitionUpdate,
    RemediationPreviewRead,
    ValidationDefinitionCreate,
    ValidationDefinitionRead,
    ValidationDefinitionUpdate,
    ValidationRunRead,
    ValidationTestRequest,
)
from app.services.automation import latest_validation_runs, run_validation_definition

router = APIRouter(tags=["automation"])


def _validation_or_404(db: Session, validation_id: int) -> ValidationDefinition:
    item = db.query(ValidationDefinition).filter(ValidationDefinition.id == validation_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Validation not found")
    return item


def _remediation_or_404(db: Session, remediation_id: int) -> RemediationDefinition:
    item = db.query(RemediationDefinition).filter(RemediationDefinition.id == remediation_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Remediation not found")
    return item


def _node_or_404(db: Session, node_id: int) -> Node:
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


def _serialize_validation(db: Session, item: ValidationDefinition) -> ValidationDefinitionRead:
    last_run = latest_validation_runs(db, item.id)
    assigned_count = db.query(NodeValidationAssignment).filter(NodeValidationAssignment.validation_id == item.id).count()
    return ValidationDefinitionRead(
        id=item.id,
        name=item.name,
        description=item.description,
        validation_type=item.validation_type,
        command=item.command,
        url=item.url,
        path=item.path,
        expected_status_code=item.expected_status_code,
        expected_exit_code=item.expected_exit_code,
        expected_response_contains=item.expected_response_contains,
        timeout_seconds=item.timeout_seconds,
        is_enabled=item.is_enabled,
        assigned_node_count=assigned_count,
        last_run_status=last_run.status if last_run else None,
        last_run_at=last_run.finished_at if last_run else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _latest_remediation_task(db: Session, remediation_id: int) -> ExecutionTask | None:
    tasks = (
        db.query(ExecutionTask)
        .filter(ExecutionTask.action_key == "automated_remediation")
        .order_by(desc(ExecutionTask.queued_at), desc(ExecutionTask.id))
        .limit(200)
        .all()
    )
    return next((task for task in tasks if task.parameters.get("remediation_definition_id") == remediation_id), None)


def _serialize_remediation(db: Session, item: RemediationDefinition) -> RemediationDefinitionRead:
    last_task = _latest_remediation_task(db, item.id)
    last_run_at = (last_task.finished_at or last_task.queued_at) if last_task else None
    assigned_count = db.query(NodeRemediationAssignment).filter(NodeRemediationAssignment.remediation_id == item.id).count()
    return RemediationDefinitionRead(
        id=item.id,
        name=item.name,
        description=item.description,
        command=item.command,
        risk_level=item.risk_level,
        execution_mode=item.execution_mode,
        is_enabled=item.is_enabled,
        assigned_node_count=assigned_count,
        last_run_status=last_task.status if last_task else None,
        last_run_at=last_run_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _serialize_validation_run(run: ValidationRun) -> ValidationRunRead:
    return ValidationRunRead(
        id=run.id,
        node_id=run.node_id,
        incident_id=run.incident_id,
        validation_id=run.validation_id,
        validation_name=run.validation.name if run.validation else None,
        status=run.status,
        matched_expectation=run.matched_expectation,
        observed_status_code=run.observed_status_code,
        observed_exit_code=run.observed_exit_code,
        output=run.output,
        error_detail=run.error_detail,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _serialize_assignments(db: Session, node_id: int) -> NodeAutomationAssignmentsRead:
    validations = (
        db.query(NodeValidationAssignment)
        .filter(NodeValidationAssignment.node_id == node_id)
        .order_by(NodeValidationAssignment.sort_order.asc(), NodeValidationAssignment.id.asc())
        .all()
    )
    remediations = (
        db.query(NodeRemediationAssignment)
        .filter(NodeRemediationAssignment.node_id == node_id)
        .order_by(NodeRemediationAssignment.sort_order.asc(), NodeRemediationAssignment.id.asc())
        .all()
    )
    edges = (
        db.query(NodeAutomationEdge)
        .filter(NodeAutomationEdge.node_id == node_id, NodeAutomationEdge.is_enabled.is_(True))
        .order_by(NodeAutomationEdge.sort_order.asc(), NodeAutomationEdge.id.asc())
        .all()
    )
    return NodeAutomationAssignmentsRead(
        node_id=node_id,
        validations=[
            NodeValidationAssignmentRead(
                id=item.id,
                node_id=item.node_id,
                validation_id=item.validation_id,
                is_enabled=item.is_enabled,
                sort_order=item.sort_order,
                validation=_serialize_validation(db, item.validation),
            )
            for item in validations
        ],
        remediations=[
            NodeRemediationAssignmentRead(
                id=item.id,
                node_id=item.node_id,
                remediation_id=item.remediation_id,
                is_enabled=item.is_enabled,
                sort_order=item.sort_order,
                remediation=_serialize_remediation(db, item.remediation),
            )
            for item in remediations
        ],
        edges=[
            NodeAutomationEdgeRead(
                id=item.id,
                node_id=item.node_id,
                validation_id=item.validation_id,
                remediation_id=item.remediation_id,
                is_enabled=item.is_enabled,
                sort_order=item.sort_order,
            )
            for item in edges
        ],
    )


@router.get("/validations", response_model=list[ValidationDefinitionRead])
def list_validations(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_serialize_validation(db, item) for item in db.query(ValidationDefinition).order_by(ValidationDefinition.name.asc()).all()]


@router.post("/validations", response_model=ValidationDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_validation(payload: ValidationDefinitionCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    item = ValidationDefinition(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_validation(db, item)


@router.put("/validations/{validation_id}", response_model=ValidationDefinitionRead)
def update_validation(validation_id: int, payload: ValidationDefinitionUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    item = _validation_or_404(db, validation_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _serialize_validation(db, item)


@router.delete("/validations/{validation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_validation(validation_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    item = _validation_or_404(db, validation_id)
    db.query(NodeAutomationEdge).filter(NodeAutomationEdge.validation_id == item.id).delete()
    db.query(NodeValidationAssignment).filter(NodeValidationAssignment.validation_id == item.id).delete()
    db.delete(item)
    db.commit()


@router.post("/validations/{validation_id}/test", response_model=ValidationRunRead)
def test_validation(
    validation_id: int,
    payload: ValidationTestRequest | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_operator_or_admin),
):
    validation = _validation_or_404(db, validation_id)
    node = _node_or_404(db, payload.node_id) if payload and payload.node_id else None
    if not node:
        assignment = db.query(NodeValidationAssignment).filter(NodeValidationAssignment.validation_id == validation.id).order_by(NodeValidationAssignment.id.asc()).first()
        node = db.query(Node).filter(Node.id == assignment.node_id).first() if assignment else db.query(Node).order_by(Node.id.asc()).first()
    if not node:
        raise HTTPException(status_code=400, detail="A node is required to test this validation")
    run = run_validation_definition(db, node=node, validation=validation)
    db.commit()
    db.refresh(run)
    return _serialize_validation_run(run)


@router.get("/remediations", response_model=list[RemediationDefinitionRead])
def list_remediations(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_serialize_remediation(db, item) for item in db.query(RemediationDefinition).order_by(RemediationDefinition.name.asc()).all()]


@router.post("/remediations", response_model=RemediationDefinitionRead, status_code=status.HTTP_201_CREATED)
def create_remediation(payload: RemediationDefinitionCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    item = RemediationDefinition(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize_remediation(db, item)


@router.put("/remediations/{remediation_id}", response_model=RemediationDefinitionRead)
def update_remediation(remediation_id: int, payload: RemediationDefinitionUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    item = _remediation_or_404(db, remediation_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _serialize_remediation(db, item)


@router.delete("/remediations/{remediation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_remediation(remediation_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    item = _remediation_or_404(db, remediation_id)
    db.query(NodeAutomationEdge).filter(NodeAutomationEdge.remediation_id == item.id).delete()
    db.query(NodeRemediationAssignment).filter(NodeRemediationAssignment.remediation_id == item.id).delete()
    db.delete(item)
    db.commit()


@router.post("/remediations/{remediation_id}/test-preview", response_model=RemediationPreviewRead)
def preview_remediation(remediation_id: int, db: Session = Depends(get_db), _: User = Depends(require_operator_or_admin)):
    item = _remediation_or_404(db, remediation_id)
    return RemediationPreviewRead(remediation_id=item.id, command=item.command, execution_mode=item.execution_mode, risk_level=item.risk_level)


@router.get("/nodes/{node_id}/automation-assignments", response_model=NodeAutomationAssignmentsRead)
def get_node_automation_assignments(node_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _node_or_404(db, node_id)
    return _serialize_assignments(db, node_id)


@router.put("/nodes/{node_id}/automation-assignments", response_model=NodeAutomationAssignmentsRead)
def update_node_automation_assignments(
    node_id: int,
    payload: NodeAutomationAssignmentsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _node_or_404(db, node_id)
    validation_ids = list(dict.fromkeys(payload.validation_ids))
    remediation_ids = list(dict.fromkeys(payload.remediation_ids))
    valid_validation_ids = set(validation_ids)
    valid_remediation_ids = set(remediation_ids)

    db.query(NodeValidationAssignment).filter(NodeValidationAssignment.node_id == node_id).delete()
    db.query(NodeRemediationAssignment).filter(NodeRemediationAssignment.node_id == node_id).delete()
    db.query(NodeAutomationEdge).filter(NodeAutomationEdge.node_id == node_id).delete()
    for index, validation_id in enumerate(validation_ids):
        _validation_or_404(db, validation_id)
        db.add(NodeValidationAssignment(node_id=node_id, validation_id=validation_id, sort_order=index, is_enabled=True))
    for index, remediation_id in enumerate(remediation_ids):
        _remediation_or_404(db, remediation_id)
        db.add(NodeRemediationAssignment(node_id=node_id, remediation_id=remediation_id, sort_order=index, is_enabled=True))
    unique_edges: set[tuple[int, int]] = set()
    for index, edge in enumerate(payload.edges):
        if edge.validation_id not in valid_validation_ids or edge.remediation_id not in valid_remediation_ids:
            raise HTTPException(status_code=400, detail="Automation playbook edge references an unassigned validation or remediation")
        key = (edge.validation_id, edge.remediation_id)
        if key in unique_edges:
            continue
        unique_edges.add(key)
        db.add(
            NodeAutomationEdge(
                node_id=node_id,
                validation_id=edge.validation_id,
                remediation_id=edge.remediation_id,
                sort_order=index,
                is_enabled=True,
            )
        )
    db.commit()
    return _serialize_assignments(db, node_id)
