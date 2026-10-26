from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Generator

import jwt
from pypdf import PdfReader
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hrmsai.db")
APP_ENV = os.getenv("APP_ENV", "development").lower()
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    if APP_ENV == "production":
        raise RuntimeError("JWT_SECRET must be set in production")
    JWT_SECRET = "development-only-change-me"
if APP_ENV == "production" and JWT_SECRET in {"change-this-before-deploying", "development-only-change-me"}:
    raise RuntimeError("JWT_SECRET must be replaced with a unique production secret")
AUTO_CREATE_SCHEMA = os.getenv("AUTO_CREATE_SCHEMA", "true").lower() == "true"
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "60"))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")
    employees: Mapped[list["Employee"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(default=True)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), default="Employee")
    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), default="Employee")
    status: Mapped[str] = mapped_column(String(40), default="Active")
    joined: Mapped[datetime] = mapped_column(Date)
    organization: Mapped[Organization] = relationship(back_populates="employees")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    leave_type: Mapped[str] = mapped_column(String(80))
    from_date: Mapped[datetime] = mapped_column(Date)
    to_date: Mapped[datetime] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(30), default="Pending")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    text_content: Mapped[str] = mapped_column(Text)
    extracted_details: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LoginRequest(BaseModel):
    email: str
    password: str


class WorkspaceRequest(LoginRequest):
    name: str = Field(min_length=2, max_length=120)
    workspace: str = Field(min_length=2, max_length=80)
    full_name: str = Field(min_length=2, max_length=120)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    organization: dict


class EmployeeInput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=2, max_length=120)
    email: str
    department: str
    title: str
    role: str = "Employee"
    status: str = "Active"
    joined: datetime


class EmployeeResponse(EmployeeInput):
    id: int


class LeaveInput(BaseModel):
    employee_id: int
    leave_type: str
    from_date: datetime
    to_date: datetime
    reason: str = ""


class LeaveResponse(LeaveInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str


class MessageInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


def extract_resume_details(text: str) -> dict:
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
    skills_catalog = ["react", "javascript", "typescript", "python", "fastapi", "sql", "postgresql", "excel", "figma", "java", "aws", "docker"]
    lower = text.lower()
    skills = [skill for skill in skills_catalog if skill in lower]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "email": email.group(0) if email else "",
        "phone": phone.group(0).strip() if phone else "",
        "skills": skills,
        "line_count": len(lines),
        "sections": {
            section: any(section in line.lower() for line in lines)
            for section in ("experience", "education", "skills", "projects", "certifications")
        },
        "text_preview": text[:1000],
    }


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_token(user: User, membership: Membership) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES)
    return jwt.encode(
        {
            "sub": str(user.id),
            "organization_id": membership.organization_id,
            "membership_id": membership.id,
            "role": membership.role,
            "exp": expires,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


bearer = HTTPBearer(auto_error=False)


def current_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> tuple[User, Membership, Organization]:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
        organization_id = int(payload["organization_id"])
        membership_id = int(payload["membership_id"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from exc

    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
    )
    user = db.get(User, user_id)
    organization = db.get(Organization, organization_id)
    if not membership or not user or not user.active or not organization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active")
    return user, membership, organization


def require_roles(*roles: str):
    def dependency(context=Depends(current_context)):
        if context[1].role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return context

    return dependency


def write_audit(db: Session, organization_id: int, actor_user_id: int, action: str, entity_type: str, entity_id: str):
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def user_payload(user: User, membership: Membership) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": membership.role}


app = FastAPI(title="HRMS AI API", version="0.1.0")
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    if AUTO_CREATE_SCHEMA:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == "neha@northstar.io")):
            return
        organization = Organization(name="Northstar Labs", slug="northstar")
        user = User(email="neha@northstar.io", name="Neha Kapoor", password_hash=hash_password("Welcome123!"))
        db.add_all([organization, user])
        db.flush()
        membership = Membership(user_id=user.id, organization_id=organization.id, role="HR/Admin")
        db.add(membership)
        db.flush()
        db.add(
            Employee(
                organization_id=organization.id,
                name=user.name,
                email=user.email,
                department="People",
                title="Head of People",
                role="HR/Admin",
                joined=datetime(2021, 5, 3),
            )
        )
        db.commit()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "hrms-ai-api"}


@app.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: WorkspaceRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.strip().lower()
    slug = payload.workspace.strip().lower().replace(" ", "-")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    if db.scalar(select(Organization).where(Organization.slug == slug)):
        raise HTTPException(status_code=409, detail="That workspace name is already in use")
    organization = Organization(name=payload.name.strip(), slug=slug)
    user = User(email=email, name=payload.full_name.strip(), password_hash=hash_password(payload.password))
    db.add_all([organization, user])
    db.flush()
    membership = Membership(user_id=user.id, organization_id=organization.id, role="HR/Admin")
    db.add(membership)
    db.flush()
    db.add(
        Employee(
            organization_id=organization.id,
            name=user.name,
            email=user.email,
            department="People",
            title="Workspace administrator",
            role="HR/Admin",
            joined=datetime.now(timezone.utc).date(),
        )
    )
    write_audit(db, organization.id, user.id, "workspace.created", "organization", str(organization.id))
    db.commit()
    return TokenResponse(
        access_token=create_token(user, membership),
        user=user_payload(user, membership),
        organization={"id": organization.id, "name": organization.name, "slug": organization.slug},
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not user.active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No workspace membership is assigned")
    organization = db.get(Organization, membership.organization_id)
    return TokenResponse(
        access_token=create_token(user, membership),
        user=user_payload(user, membership),
        organization={"id": organization.id, "name": organization.name, "slug": organization.slug},
    )


@app.get("/auth/me")
def me(context=Depends(current_context)) -> dict:
    user, membership, organization = context
    return {"user": user_payload(user, membership), "organization": {"id": organization.id, "name": organization.name, "slug": organization.slug}}


@app.get("/employees", response_model=list[EmployeeResponse])
def list_employees(context=Depends(current_context), db: Session = Depends(get_db)) -> list[Employee]:
    _, _, organization = context
    return list(db.scalars(select(Employee).where(Employee.organization_id == organization.id).order_by(Employee.id)))


@app.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(payload: EmployeeInput, context=Depends(require_roles("HR/Admin", "System Administrator")), db: Session = Depends(get_db)) -> Employee:
    user, _, organization = context
    employee = Employee(organization_id=organization.id, **payload.model_dump())
    db.add(employee)
    db.flush()
    write_audit(db, organization.id, user.id, "employee.created", "employee", str(employee.id))
    db.commit()
    db.refresh(employee)
    return employee


@app.get("/leaves", response_model=list[LeaveResponse])
def list_leaves(context=Depends(current_context), db: Session = Depends(get_db)) -> list[LeaveRequest]:
    _, _, organization = context
    return list(db.scalars(select(LeaveRequest).where(LeaveRequest.organization_id == organization.id).order_by(LeaveRequest.id.desc())))


@app.post("/leaves", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
def create_leave(payload: LeaveInput, context=Depends(current_context), db: Session = Depends(get_db)) -> LeaveRequest:
    user, _, organization = context
    employee = db.scalar(select(Employee).where(Employee.id == payload.employee_id, Employee.organization_id == organization.id))
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found in this workspace")
    if payload.to_date < payload.from_date:
        raise HTTPException(status_code=422, detail="Leave end date cannot be before start date")
    leave = LeaveRequest(organization_id=organization.id, **payload.model_dump())
    db.add(leave)
    db.flush()
    write_audit(db, organization.id, user.id, "leave.created", "leave_request", str(leave.id))
    db.commit()
    db.refresh(leave)
    return leave


@app.get("/messages")
def list_messages(context=Depends(current_context), db: Session = Depends(get_db)) -> list[dict]:
    _, _, organization = context
    rows = db.execute(
        select(Message, User.name)
        .join(User, User.id == Message.sender_user_id)
        .where(Message.organization_id == organization.id)
        .order_by(Message.created_at)
    ).all()
    return [{"id": message.id, "sender": sender, "text": message.text, "time": message.created_at.isoformat()} for message, sender in rows]


@app.post("/messages", status_code=status.HTTP_201_CREATED)
def create_message(payload: MessageInput, context=Depends(current_context), db: Session = Depends(get_db)) -> dict:
    user, _, organization = context
    message = Message(organization_id=organization.id, sender_user_id=user.id, text=payload.text.strip())
    db.add(message)
    db.flush()
    write_audit(db, organization.id, user.id, "message.created", "message", str(message.id))
    db.commit()
    return {"id": message.id, "sender": user.name, "text": message.text, "time": message.created_at.isoformat()}


@app.post("/resumes", status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), context=Depends(require_roles("HR/Admin", "Manager")), db: Session = Depends(get_db)) -> dict:
    user, _, organization = context
    allowed = {"text/plain", "text/markdown", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Upload a TXT, Markdown, or PDF resume")
    raw = await file.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=413, detail="Resume must be smaller than 5 MB")
    if file.content_type == "application/pdf":
        import io

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    else:
        text = raw.decode("utf-8", errors="ignore")
    details = extract_resume_details(text)
    resume = Resume(
        organization_id=organization.id,
        filename=file.filename or "resume.txt",
        content_type=file.content_type,
        text_content=text,
        extracted_details=details,
        uploaded_by=user.id,
    )
    db.add(resume)
    db.flush()
    write_audit(db, organization.id, user.id, "resume.uploaded", "resume", str(resume.id))
    db.commit()
    return {"id": resume.id, "filename": resume.filename, "details": details}
