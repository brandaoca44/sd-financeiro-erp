"""Cadastro profissional de colaboradores, separado dos dados financeiros."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, field_validator
from sqlalchemy import Date, ForeignKeyConstraint, Numeric, String, Text, Uuid, select
from sqlalchemy.orm import mapped_column

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.database.base import Base
from app.modules.finance.schemas import Money
from app.modules.people.payroll_preview import estimate_clt_2026
from app.modules.identity.account_security import RegisterRequest
from app.modules.identity.pix import PixDetails, normalize_passport
from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.organizations.models import Company, CompanyStatus, Organization


class Collaborator(Base):
    __tablename__ = "people_collaborators"
    __table_args__ = (ForeignKeyConstraint(
        ["organization_id", "company_id"], ["companies.organization_id", "companies.id"],
        name="fk_people_collaborators_company", ondelete="RESTRICT",
    ),)
    organization_id = mapped_column(Uuid, primary_key=True)
    company_id = mapped_column(Uuid, primary_key=True)
    id = mapped_column(Uuid, primary_key=True)
    name = mapped_column(String(150), nullable=False)
    job_title = mapped_column(String(100), nullable=False)

    employment_type = mapped_column(String(20))
    work_model = mapped_column(String(20))
    admission_date = mapped_column(Date)
    monthly_compensation = mapped_column(Numeric)
    private_data = mapped_column(Text)
    termination_date = mapped_column(Date)
    termination_reason = mapped_column(String(30))


class CollaboratorSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", hide_input_in_errors=True)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    job_title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    employment_type: Literal["CLT", "PJ", "ESTAGIO", "TEMPORARIO", "OUTRO"] | None = None
    work_model: Literal["PRESENCIAL", "HIBRIDO", "REMOTO"] | None = None
    admission_date: date | None = None


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]


class PrivateDetails(PixDetails):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    monthly_compensation: Money | None = None
    cpf: Annotated[str, StringConstraints(pattern=r"^\d{11}$")] | None = None
    rg: ShortText | None = None
    cnh: ShortText | None = None
    passport: ShortText | None = None
    birth_date: date | None = None
    birthplace: LongText | None = None
    cep: Annotated[str, StringConstraints(pattern=r"^[0-9]{8}$")] | None = None
    address: LongText | None = None
    phone: ShortText | None = None
    bank: ShortText | None = None
    branch: ShortText | None = None
    account: ShortText | None = None
    account_type: Literal["CORRENTE", "POUPANCA", "SALARIO", "PAGAMENTO"] | None = None


class RequiredPrivateDetails(PrivateDetails):
    @field_validator("passport")
    @classmethod
    def validate_passport(cls, value):
        return normalize_passport(value)

    rg: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,80}$")] | None = None
    cnh: Annotated[str, StringConstraints(pattern=r"^[0-9]{11}$")] | None = None
    cpf: Annotated[str, StringConstraints(pattern=r"^[0-9]{11}$")]
    phone: Annotated[str, StringConstraints(pattern=r"^[0-9]{10,11}$")]
    bank: ShortText
    branch: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,80}$")]
    account: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,80}$")]
    account_type: Literal["CORRENTE", "POUPANCA", "SALARIO", "PAGAMENTO"]

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, value: str) -> str:
        RegisterRequest.cpf_valid(SecretStr(value))
        return value


class CollaboratorCreate(CollaboratorSummary):
    details: RequiredPrivateDetails


class CollaboratorResponse(CollaboratorSummary):
    id: UUID
    termination_date: date | None = None
    termination_reason: str | None = None


class TerminationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    reason: Literal["JUSTA_CAUSA", "SEM_JUSTA_CAUSA", "PEDIDO_DEMISSAO",
                    "FIM_CONTRATO", "ACORDO", "OUTRO"]


def cipher(request: Request) -> Fernet:
    key = request.app.state.settings.auth_identity_encryption_key
    if key is None:
        raise HTTPException(503, "Cadastro protegido temporariamente indisponível.")
    return Fernet(key.get_secret_value().encode("ascii"))


def read_details(row, request):
    if row.private_data is None:
        return PrivateDetails(monthly_compensation=row.monthly_compensation)
    try:
        return PrivateDetails.model_validate_json(cipher(request).decrypt(row.private_data.encode("ascii")))
    except InvalidToken:
        raise HTTPException(503, "Cadastro protegido temporariamente indisponível.") from None


def store_details(row, details, request):
    row.private_data = cipher(request).encrypt(details.model_dump_json().encode()).decode("ascii")
    row.monthly_compensation = None


router = APIRouter(
    prefix="/organizations/{organization_id}/companies/{company_id}/collaborators",
    tags=["Pessoas"],
)


def visible_company(user_id, organization_id, company_id):
    owner = select(OrganizationOwnership.user_id).where(
        OrganizationOwnership.organization_id == organization_id, OrganizationOwnership.user_id == user_id,
    ).exists()
    return select(Company.id).where(
        Company.organization_id == organization_id, Company.id == company_id,
        Company.status == CompanyStatus.ACTIVE, owner,
        CompanyAccessPolicy._active_actor(user_id, organization_id),
    ).exists()


@router.get("", response_model=list[CollaboratorResponse])
async def list_collaborators(organization_id: UUID, company_id: UUID, request: Request,
                             current=Depends(get_current_session), token=Depends(get_session_token)):
    visible = visible_company(current.user_id, organization_id, company_id)
    async with request.app.state.session_factory() as session:
        if not await session.scalar(select(visible)):
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        rows = await session.scalars(select(Collaborator).where(
            Collaborator.organization_id == organization_id, Collaborator.company_id == company_id, visible,
        ).order_by(Collaborator.name, Collaborator.id))
        result = [CollaboratorResponse.model_validate(row) for row in rows]
    await record_authorized_activity(request, token)
    return result


@router.post("", response_model=CollaboratorResponse, status_code=201)
async def create_collaborator(organization_id: UUID, company_id: UUID, data: CollaboratorCreate,
                              request: Request, request_id: UUID = Header(alias="Idempotency-Key"),
                              current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session, session.begin():
        await session.scalar(select(Organization.id).where(Organization.id == organization_id).with_for_update())
        if not await session.scalar(select(visible_company(current.user_id, organization_id, company_id))):
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        await record_authorized_activity(request, token)
        row = await session.get(Collaborator, (organization_id, company_id, request_id))
        if row is None:
            row = Collaborator(organization_id=organization_id, company_id=company_id,
                               id=request_id, **data.model_dump(exclude={"details"}))
            store_details(row, data.details, request)
            session.add(row)
        elif any(getattr(row, key) != value for key, value in data.model_dump(exclude={"details"}).items()) or read_details(row, request).model_dump() != data.details.model_dump():
            raise HTTPException(409, "Cadastro já processado com outros dados.")
        return CollaboratorResponse.model_validate(row)


@router.put("/{collaborator_id}", response_model=CollaboratorResponse)
async def update_collaborator(organization_id: UUID, company_id: UUID, collaborator_id: UUID,
                              data: CollaboratorCreate, request: Request,
                              current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session, session.begin():
        await session.scalar(select(Organization.id).where(Organization.id == organization_id).with_for_update())
        if not await session.scalar(select(visible_company(current.user_id, organization_id, company_id))):
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        row = await session.get(Collaborator, (organization_id, company_id, collaborator_id))
        if row is None:
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        await record_authorized_activity(request, token)
        if row.termination_date and data.admission_date != row.admission_date:
            raise HTTPException(409, "A admissão de um vínculo encerrado faz parte do histórico.")
        for key, value in data.model_dump(exclude={"details"}).items():
            setattr(row, key, value)
        store_details(row, data.details, request)
        return CollaboratorResponse.model_validate(row)


@router.get("/{collaborator_id}/details", response_model=PrivateDetails)
async def collaborator_details(organization_id: UUID, company_id: UUID, collaborator_id: UUID,
                               request: Request, response: Response,
                               current=Depends(get_current_session), token=Depends(get_session_token)):
    visible = visible_company(current.user_id, organization_id, company_id)
    async with request.app.state.session_factory() as session:
        row = await session.scalar(select(Collaborator).where(
            Collaborator.organization_id == organization_id, Collaborator.company_id == company_id,
            Collaborator.id == collaborator_id, visible,
        ))
        if row is None:
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        details = read_details(row, request)
    await record_authorized_activity(request, token)
    response.headers["Cache-Control"] = "no-store"
    return details


@router.get("/{collaborator_id}/payroll-preview-2026", response_model=dict[str, Decimal])
async def payroll_preview(organization_id: UUID, company_id: UUID, collaborator_id: UUID,
                          request: Request, response: Response,
                          current=Depends(get_current_session), token=Depends(get_session_token)):
    if request.app.state.settings.app_environment != "development":
        raise HTTPException(404, "Prévia de folha indisponível.")
    async with request.app.state.session_factory() as session:
        row = await session.scalar(select(Collaborator).where(
            Collaborator.organization_id == organization_id, Collaborator.company_id == company_id,
            Collaborator.id == collaborator_id, visible_company(current.user_id, organization_id, company_id),
        ))
        if row is None:
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        if row.employment_type != "CLT":
            raise HTTPException(422, "A prévia se aplica a vínculos CLT.")
        gross = read_details(row, request).monthly_compensation
    if gross is None:
        raise HTTPException(422, "Informe a remuneração bruta.")
    await record_authorized_activity(request, token)
    response.headers["Cache-Control"] = "no-store"
    return estimate_clt_2026(gross)


@router.post("/{collaborator_id}/termination", response_model=CollaboratorResponse)
async def terminate_collaborator(organization_id: UUID, company_id: UUID, collaborator_id: UUID,
                                  data: TerminationRequest, request: Request,
                                  current=Depends(get_current_session), token=Depends(get_session_token)):
    async with request.app.state.session_factory() as session, session.begin():
        await session.scalar(select(Organization.id).where(Organization.id == organization_id).with_for_update())
        if not await session.scalar(select(visible_company(current.user_id, organization_id, company_id))):
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        row = await session.get(Collaborator, (organization_id, company_id, collaborator_id))
        if row is None:
            raise HTTPException(404, "Cadastro de colaboradores indisponível.")
        if row.termination_date and (row.termination_date, row.termination_reason) != (data.date, data.reason):
            raise HTTPException(409, "O vínculo já foi encerrado.")
        if row.admission_date and data.date < row.admission_date:
            raise HTTPException(422, "O desligamento deve ocorrer a partir da data de admissão.")
        await record_authorized_activity(request, token)
        row.termination_date = data.date
        row.termination_reason = data.reason
        return CollaboratorResponse.model_validate(row)
