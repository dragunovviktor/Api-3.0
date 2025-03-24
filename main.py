from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import uuid

DATABASE_URL = "postgresql://sber_admin:securepass@db:5432/sber_api"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Модели базы данных
class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, index=True)
    internal_code = Column(String, unique=True)
    latitude = Column(Float)
    longitude = Column(Float)


class ObjectType(Base):
    __tablename__ = "object_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)  # газон, крыльцо, тротуар
    measure_unit = Column(String)  # м², пог. м


class BranchObject(Base):
    __tablename__ = "branch_objects"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    object_type_id = Column(Integer, ForeignKey("object_types.id"))
    name = Column(String)
    area = Column(Float)
    description = Column(String)


class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    object_id = Column(Integer, ForeignKey("branch_objects.id"), nullable=True)
    work_type = Column(String)
    frequency = Column(String)
    next_maintenance_date = Column(DateTime)


class CompletedWork(Base):
    __tablename__ = "completed_works"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    object_id = Column(Integer, ForeignKey("branch_objects.id"), nullable=True)
    work_type = Column(String)
    completion_date = Column(DateTime)
    responsible_person = Column(String)
    notes = Column(Text)


class BranchAttachment(Base):
    __tablename__ = "branch_attachments"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    object_id = Column(Integer, ForeignKey("branch_objects.id"), nullable=True)
    file_type = Column(String)  # фото, схема, план
    file_url = Column(String)
    uploaded_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sber Branches API",
    description="API для управления территориями отделений Сбербанка",
    version="1.0.0",
    docs_url="/docs",  # Измените на /docs вместо /api/docs
    redoc_url="/redoc"  # Измените на /redoc вместо /api/redoc
)

# Pydantic модели
class BranchCreate(BaseModel):
    address: str
    internal_code: str
    latitude: float
    longitude: float


class ObjectCreate(BaseModel):
    branch_id: int
    object_type_id: int
    name: str
    area: float
    description: Optional[str] = None


class MaintenancePlanCreate(BaseModel):
    branch_id: int
    object_id: Optional[int] = None
    work_type: str
    frequency: str
    next_maintenance_date: datetime


class CompletedWorkCreate(BaseModel):
    branch_id: int
    object_id: Optional[int] = None
    work_type: str
    completion_date: datetime
    responsible_person: str
    notes: Optional[str] = None


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Эндпоинты для администраторов
@app.post("/api/branches", response_model=BranchCreate)
def create_branch(branch: BranchCreate, db: Session = Depends(get_db)):
    db_branch = Branch(**branch.dict())
    db.add(db_branch)
    db.commit()
    db.refresh(db_branch)
    return db_branch


@app.put("/api/branches/{branch_id}", response_model=BranchCreate)
def update_branch(branch_id: int, branch: BranchCreate, db: Session = Depends(get_db)):
    db_branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not db_branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    for var, value in vars(branch).items():
        setattr(db_branch, var, value) if value else None
    db.commit()
    db.refresh(db_branch)
    return db_branch


@app.post("/api/objects", response_model=ObjectCreate)
def create_object(obj: ObjectCreate, db: Session = Depends(get_db)):
    db_object = BranchObject(**obj.dict())
    db.add(db_object)
    db.commit()
    db.refresh(db_object)
    return db_object


@app.post("/api/maintenance", response_model=MaintenancePlanCreate)
def create_maintenance_plan(plan: MaintenancePlanCreate, db: Session = Depends(get_db)):
    db_plan = MaintenancePlan(**plan.dict())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@app.post("/api/completed-works", response_model=CompletedWorkCreate)
def create_completed_work(work: CompletedWorkCreate, db: Session = Depends(get_db)):
    db_work = CompletedWork(**work.dict())
    db.add(db_work)
    db.commit()
    db.refresh(db_work)
    return db_work


@app.post("/api/attachments")
async def upload_attachment(
        branch_id: int,
        object_id: Optional[int] = None,
        file_type: str = "photo",
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    # Сохраняем файл
    file_location = f"uploads/{uuid.uuid4()}_{file.filename}"
    os.makedirs("uploads", exist_ok=True)
    with open(file_location, "wb+") as file_object:
        file_object.write(await file.read())

    # Создаем запись в БД
    db_attachment = BranchAttachment(
        branch_id=branch_id,
        object_id=object_id,
        file_type=file_type,
        file_url=file_location
    )
    db.add(db_attachment)
    db.commit()
    db.refresh(db_attachment)
    return {"filename": file.filename, "location": file_location}


# Эндпоинты для чат-бота
@app.get("/api/branches", response_model=List[BranchCreate])
def search_branches(search: str = "", db: Session = Depends(get_db)):
    return db.query(Branch).filter(
        (Branch.address.ilike(f"%{search}%")) |
        (Branch.internal_code.ilike(f"%{search}%"))
    ).all()


@app.get("/api/branches/{branch_id}/objects", response_model=List[ObjectCreate])
def get_branch_objects(branch_id: int, db: Session = Depends(get_db)):
    return db.query(BranchObject).filter(BranchObject.branch_id == branch_id).all()


@app.get("/api/branches/{branch_id}/plans", response_model=List[MaintenancePlanCreate])
def get_branch_plans(branch_id: int, db: Session = Depends(get_db)):
    return db.query(MaintenancePlan).filter(MaintenancePlan.branch_id == branch_id).all()


@app.get("/api/branches/{branch_id}/completed-works", response_model=List[CompletedWorkCreate])
def get_branch_completed_works(branch_id: int, db: Session = Depends(get_db)):
    return db.query(CompletedWork).filter(CompletedWork.branch_id == branch_id).all()


@app.get("/api/branches/{branch_id}/attachments", response_model=List[dict])
def get_branch_attachments(branch_id: int, db: Session = Depends(get_db)):
    attachments = db.query(BranchAttachment).filter(BranchAttachment.branch_id == branch_id).all()
    return [{"file_type": a.file_type, "file_url": a.file_url} for a in attachments]


# NLP обработка запросов
@app.get("/api/nlp-query")
def process_nlp_query(query: str, db: Session = Depends(get_db)):
    # Простейшая реализация NLP обработки
    if "планируется" in query.lower() or "планы" in query.lower():
        # Ищем номер ВСП в запросе
        branch_code = "".join([c for c in query if c.isdigit()])
        if branch_code:
            return get_branch_plans(int(branch_code), db)

    elif "выполнено" in query.lower() or "сделано" in query.lower():
        branch_code = "".join([c for c in query if c.isdigit()])
        if branch_code:
            return get_branch_completed_works(int(branch_code), db)

    return {"message": "Не удалось обработать запрос. Уточните параметры поиска."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9080)