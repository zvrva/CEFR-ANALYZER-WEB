import uuid

from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Boolean, UUID, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

from pydantic import BaseModel
from typing import List, Optional, Literal




Base = declarative_base()

class Texts(Base):
    __tablename__ = 'texts'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(UUID,  nullable=False, server_default=func.gen_random_uuid())
    text = Column(String, nullable=False)
    linguistic_report = Column(JSON, nullable=False)
    level_id = Column(UUID, server_default=func.gen_random_uuid())
    is_from_csv = Column(Boolean, nullable=False, default=False)  
    analyzed_at = Column(DateTime(timezone=True), nullable=True)  

    # level = relationship("Levels", back_populates="level_id")

class TextsCRUD(BaseModel):
    user_id: Optional[str] = None
    text: str
    linguistic_report: dict
    level_id: str
    is_from_csv: bool = False
    analyzed_at: Optional[str] = None

    def add(self, db: Session):
        new_text = Texts(
            id=func.gen_random_uuid(),
            user_id=self.user_id,
            text=self.text,
            level_id=self.level_id,
            linguistic_report=self.linguistic_report,
            is_from_csv=self.is_from_csv,
            analyzed_at=self.analyzed_at
        )
        db.add(new_text)
        db.commit()
        db.refresh(new_text)
        return new_text


class Levels(Base):
    __tablename__ = 'levels'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    level = Column(String(2), nullable=False)
    description = Column(String, nullable=True)

    # level_id = relationship("Texts", back_populates="level")


class LevelsCRUD(BaseModel):
    level: str
    description: Optional[str] = None

    def find(self, db: Session):
        return db.query(Levels.id).filter(Levels.level == self.level).scalar()


class Errors(Base):
    __tablename__ = 'errors'

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    text = Column(String(15), nullable=False)
    description = Column(String, nullable=True)


class ErrorsCRUD(BaseModel):
    text: str
    description: Optional[str] = None

    def add(self, db: Session):
        new_error = Errors(
            id=func.gen_random_uuid(),
            text=self.text,
            description=self.description
        )
        db.add(new_error)
        db.commit()
        db.refresh(new_error)
        # return new_error

    def find(self, db: Session):
        return db.query(Errors.id).filter(Errors.text == self.text).first()
   





class Users(Base):
    __tablename__ = "users"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)

    email = Column(String(50), unique=True, nullable=False, index=True)

    surname = Column(String, nullable=False)
    name = Column(String, nullable=False)

    hash_password = Column(String, nullable=False)


class UsersCRUD(BaseModel):
    email: Optional[str] = None
    surname: Optional[str] = None
    name: Optional[str] = None
    password: Optional[str] = None

    def add(self, db: Session):
        new_user = Users(
            id=func.gen_random_uuid(),
            email=self.email,
            surname=self.surname,
            name=self.name,
            hash_password=self.password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        # return new_user

    def find(self, db: Session):
        return db.query(Users).filter(Users.email == self.email).first()




