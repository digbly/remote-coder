import asyncio
from dataclasses import dataclass
from uuid import uuid4

APPROVAL_TIMEOUT_SECONDS = 120
MAX_PENDING_APPROVALS = 100


class ApprovalCapacityError(Exception):
    pass


@dataclass
class PendingApproval:
    approval_id: str
    user_id: int
    project_id: int
    command: str
    decision: asyncio.Future[bool]


_pending: dict[str, PendingApproval] = {}


def create_approval(user_id: int, project_id: int, command: str) -> PendingApproval:
    if len(_pending) >= MAX_PENDING_APPROVALS:
        raise ApprovalCapacityError("too many pending command approvals")
    approval_id = uuid4().hex
    pending = PendingApproval(
        approval_id=approval_id,
        user_id=user_id,
        project_id=project_id,
        command=command,
        decision=asyncio.get_running_loop().create_future(),
    )
    _pending[approval_id] = pending
    return pending


async def wait_for_decision(pending: PendingApproval) -> bool:
    try:
        return await asyncio.wait_for(pending.decision, timeout=APPROVAL_TIMEOUT_SECONDS)
    finally:
        _pending.pop(pending.approval_id, None)


def discard_approval(pending: PendingApproval) -> None:
    _pending.pop(pending.approval_id, None)
    if not pending.decision.done():
        pending.decision.cancel()


def resolve_approval(
    approval_id: str,
    user_id: int,
    project_id: int,
    approved: bool,
) -> bool:
    pending = _pending.get(approval_id)
    if (
        pending is None
        or pending.user_id != user_id
        or pending.project_id != project_id
        or pending.decision.done()
    ):
        return False
    pending.decision.set_result(approved)
    return True


def cancel_all() -> None:
    for pending in _pending.values():
        if not pending.decision.done():
            pending.decision.set_result(False)
