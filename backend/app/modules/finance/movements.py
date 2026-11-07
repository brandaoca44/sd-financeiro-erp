"""Baixa/estorno manuais com saldo exato, locks e idempotência transacional."""

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import secrets
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select, text

from app.modules.finance.account_posting import posting_account
from app.modules.finance.models import Payable, PayableChange, PayableMovement, PayableMovementRequest
from app.modules.finance.schemas import MovementReceipt, MovementResponse, PayablePosition
from app.modules.finance.service import PayableService, PayableConflictError
from app.modules.identity.access_security import AccessRevisionConflictError
from app.modules.identity.permissions import PermissionKey


class PayableMovementService(PayableService):
    async def _net(self, title):
        net = await self.session.scalar(select(func.coalesce(func.sum(case(
            (PayableMovement.kind == "PAYMENT", PayableMovement.amount), else_=-PayableMovement.amount)), 0)).where(
                PayableMovement.organization_id == title.organization_id, PayableMovement.company_id == title.company_id,
                PayableMovement.payable_id == title.id))
        if not Decimal(0) <= net <= title.amount:
            raise PayableConflictError()
        return net

    @staticmethod
    def _receipt(saved):
        return MovementReceipt(payable_id=saved.payable_id, movement_id=saved.movement_id,
                               revision=saved.title_revision, kind=saved.operation)

    @staticmethod
    def _today():
        return datetime.now(timezone.utc).astimezone(ZoneInfo("America/Sao_Paulo")).date()

    async def _move(self, organization_id, company_id, payable_id, data, token, request_key, *, payment_id=None):
        operation = "PAYMENT" if payment_id is None else "REVERSAL"
        permission = PermissionKey.PAYABLES_SETTLE if payment_id is None else PermissionKey.PAYABLES_REVERSE
        payload = {"v":1, "payable_id":str(payable_id), "expected_revision":data.expected_revision,
                   "occurred_on":data.occurred_on.isoformat(), "operation":operation}
        if payment_id is None:
            payload["amount"] = format(data.amount, ".2f")
            if data.financial_account_id is not None:
                payload["financial_account_id"] = str(data.financial_account_id)
        else:
            payload.update(payment_id=str(payment_id), reason=data.reason)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        async with self.session.begin():
            actor = await self._authorize_write(organization_id, company_id, token, permission_key=permission)
            saved = await self.session.get(PayableMovementRequest, (organization_id, company_id, actor, operation, request_key))
            if saved is not None:
                if not secrets.compare_digest(saved.payload_hash, digest):
                    raise PayableConflictError()
                return self._receipt(saved)
            title = await self.repository.get(organization_id, company_id, payable_id, lock=True)
            if title is None:
                self.deny()
            if title.revision != data.expected_revision:
                raise AccessRevisionConflictError()
            if title.status != "OPEN" or not title.issue_date <= data.occurred_on <= self._today():
                raise PayableConflictError()
            net = await self._net(title)
            if payment_id is None:
                amount, reason = data.amount, None
                if amount > title.amount - net:
                    raise PayableConflictError()
            else:
                source = await self.session.scalar(select(PayableMovement).where(
                    PayableMovement.organization_id == organization_id, PayableMovement.company_id == company_id,
                    PayableMovement.payable_id == payable_id, PayableMovement.id == payment_id,
                    PayableMovement.kind == "PAYMENT").with_for_update())
                if source is None:
                    self.deny()
                reversed_already = await self.session.scalar(select(PayableMovement.id).where(
                    PayableMovement.organization_id == organization_id, PayableMovement.company_id == company_id,
                    PayableMovement.payable_id == payable_id, PayableMovement.reverses_id == payment_id).limit(1))
                if reversed_already is not None or data.occurred_on < source.occurred_on or source.amount > net:
                    raise PayableConflictError()
                amount, reason = source.amount, data.reason
            account_id = data.financial_account_id if payment_id is None else source.financial_account_id
            await posting_account(self.session, organization_id, company_id, actor, account_id, data.occurred_on, reversal=payment_id is not None)
            before = {"revision":title.revision, "paid_amount":format(net, ".2f")}
            movement = PayableMovement(organization_id=organization_id, company_id=company_id, payable_id=payable_id,
                financial_account_id=account_id, actor_user_id=actor, kind=operation, amount=amount, occurred_on=data.occurred_on,
                reverses_id=payment_id, reversal_reason=reason)
            self.session.add(movement)
            title.revision += 1
            await self.session.flush()
            after_net = net + amount if payment_id is None else net - amount
            self.session.add(PayableChange(organization_id=organization_id, company_id=company_id, payable_id=payable_id,
                actor_user_id=actor, action=operation, before_state=before,
                after_state={"revision":title.revision, "movement_id":str(movement.id), "paid_amount":format(after_net, ".2f")}))
            saved = PayableMovementRequest(organization_id=organization_id, company_id=company_id, actor_user_id=actor,
                operation=operation, request_key=request_key, payload_hash=digest, payable_id=payable_id,
                movement_id=movement.id, title_revision=title.revision)
            self.session.add(saved)
            await self.session.flush()
            result = self._receipt(saved)
        return result

    async def pay(self, organization_id, company_id, payable_id, data, *, token, request_key):
        return await self._move(organization_id, company_id, payable_id, data, token, request_key)

    async def reverse(self, organization_id, company_id, payable_id, payment_id, data, *, token, request_key):
        return await self._move(organization_id, company_id, payable_id, data, token, request_key, payment_id=payment_id)

    async def _read_title(self, organization_id, company_id, payable_id, actor_id, *, lock=False):
        title = await self.repository.get(organization_id, company_id, payable_id, lock=lock,
            visibility=self._visibility(actor_id, organization_id))
        if title is None:
            self.deny()
        return title

    async def position(self, organization_id, company_id, payable_id, actor_id):
        # O lock do título evita misturar uma revisão com movimentos de outra revisão.
        await self.session.execute(text("SET LOCAL lock_timeout = '5s'"))
        title = await self._read_title(organization_id, company_id, payable_id, actor_id, lock=True)
        net = await self._net(title)
        if title.status == "CANCELLED" and net != 0:
            raise PayableConflictError()
        status = "CANCELLED" if title.status == "CANCELLED" else "OPEN" if net == 0 else "PAID" if net == title.amount else "PARTIALLY_PAID"
        return PayablePosition(payable_id=title.id, revision=title.revision, amount=title.amount,
            paid_amount=net, outstanding_amount=Decimal(0) if title.status == "CANCELLED" else title.amount-net, settlement_status=status)

    async def list_movements(self, organization_id, company_id, payable_id, actor_id, *, cursor=None, limit=50):
        await self._read_title(organization_id, company_id, payable_id, actor_id)
        query = select(PayableMovement).where(PayableMovement.organization_id == organization_id,
            PayableMovement.company_id == company_id, PayableMovement.payable_id == payable_id,
            select(Payable.id).where(Payable.id == PayableMovement.payable_id,
                Payable.organization_id == organization_id, Payable.company_id == company_id,
                self._visibility(actor_id, organization_id)).correlate(PayableMovement).exists())
        if cursor is not None:
            query = query.where(PayableMovement.id > cursor)
        rows = list((await self.session.scalars(query.order_by(PayableMovement.id).limit(limit+1))).all())
        return {"items":[MovementResponse.model_validate(row) for row in rows[:limit]],
                "next_cursor":rows[limit-1].id if len(rows)>limit else None}
