import os
from pathlib import Path

import re
import pandas as pd
from random import choice
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Depends
from fastapi.responses import FileResponse

from sqlalchemy.orm import Session

import torch

from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from models import Users
from db import get_db

if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(Path(__file__).resolve().parent / ".hf")

from transformers import AutoTokenizer, AutoModelForSequenceClassification

from db import get_db
from models import LevelsCRUD, Texts, Levels, ErrorsCRUD, TextsCRUD, UsersCRUD
from schemas import HistoryRequest, RegisterRequest, LoginRequest
from utils import clean_russian_words_only, clean_text, create_linguistic_report, level_to_cefr, is_text_meaningful, is_text_analyzable, validate_password_complexity, get_current_user, create_access_token, verify_password, hash_password


app = FastAPI()


class TextClassifierService:
    def __init__(self, checkpoint_path: str):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        checkpoint = torch.load(checkpoint_path, map_location=self.device)

        self.base_model_name = checkpoint["base_model_name"]
        self.num_labels = checkpoint["num_labels"]
        self.id2label = checkpoint["id2label"]
        self.label2id = checkpoint["label2id"]
        self.max_length = checkpoint.get("max_length", 512)

        self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_name)

        self.model = AutoModelForSequenceClassification.from_pretrained(
            self.base_model_name,
            num_labels=self.num_labels,
            id2label=self.id2label,
            label2id=self.label2id
        )

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.to(self.device)
        self.model.eval()

    def predict(self, text: str) -> dict:
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=self.max_length
        )

        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.inference_mode():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1)
            pred_id = torch.argmax(probs, dim=-1).item()

        return self.id2label[pred_id]

classifier = None
@app.on_event("startup")
def load_model():
    global classifier
    classifier = TextClassifierService("models/rubert_tiny.pt")
    print("Модель загружена")






@app.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):

    if UsersCRUD(email=req.email).find(db):
        return {"error": "User with this email already exists."}
    
    if len(req.surname) < 2:
        return {"error": "Surname must be at least 2 characters long."}

    if len(req.surname) > 30:
        return {"error": "Surname must be less than 30 characters long."}

    if len(req.name) < 2:
        return {"error": "Name must be at least 2 characters long."}
    
    if len(req.name) > 30:
        return {"error": "Name must be less than 30 characters long."}
    
    if validate_password_complexity(req.password):
        return {"error": validate_password_complexity(req.password)}

    UsersCRUD(
        email=req.email,
        surname=req.surname,
        name=req.name,
        password=hash_password(req.password)
    ).add(db)

    return 'Пользователь добавлен'




@app.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user= UsersCRUD(email=req.email).find(db)

    if not user:
        return {'error': 'There is no user with this email.'}

    hashed_password = user.hash_password
    if not verify_password(req.password, hashed_password):
        return {'error': 'Wrong password.'}
    
    access_token = create_access_token(user.id)

    return access_token








@app.post("/analyze")
def analyze(text: str, db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):

    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    if len(text.split()) < 5:
        errors = ErrorsCRUD(text=text).find(db)
        if not errors:
            ErrorsCRUD(text=text, description='TOO SHORT').add(db)
        return {"error": "Text is too short. Please provide a text with at least 5 words."}
    
    elif len(text.split()) > 512:
        errors = ErrorsCRUD(text=text).find(db)
        if not errors:
            ErrorsCRUD(text=text, description='TOO LONG').add(db)
        return {"error": "Text is too long. Please provide a text with no more than 512 words."}
    
    russian_text = clean_russian_words_only(text)
    if len(russian_text.split()) < 5:
        errors = ErrorsCRUD(text=text).find(db)
        if not errors:
            ErrorsCRUD(text=text, description='TOO SHORT').add(db)
        return {"error": "Text contains too few Russian words. Please provide a text with at least 5 Russian words."}
    
    text = clean_text(text)

    if not is_text_analyzable(text):
        errors = ErrorsCRUD(text=text).find(db)
        if not errors:
            ErrorsCRUD(text=text, description='NOT MEANINGFUL').add(db)
        return {"error": "The text is not meaningful. Please provide a meaningful text."}

    
    now = datetime.now()

    linguistic_report = create_linguistic_report(text)

    print(f"Linguistic report: {linguistic_report}" )

    level_cefr = classifier.predict(text)
    
    level_id = LevelsCRUD(level=level_cefr).find(db)

    print(level_id, type(level_id))

    TextsCRUD(
        user_id=current_user.id,
        text=text,
        linguistic_report=linguistic_report,
        level_id=str(level_id),
        is_from_csv=False,
        analyzed_at=now.strftime("%Y-%m-%d %H:%M:%S")
    ).add(db)


    return {
        "level": level_cefr,
        "linguistic_report": linguistic_report
    }

    
@app.post("/upload")
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    df = pd.read_csv(file.file, encoding='utf-8', header=None)
    
    file.file.close()

    results = []

    for text in df[0]:

        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        if len(text.split()) < 5:
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='TOO SHORT').add(db)
            results.append("Text is too short. Please provide a text with at least 5 words.")
            continue
        
        if len(text.split()) > 512:
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='TOO LONG').add(db)
            results.append("Text is too long. Please provide a text with no more than 512 words.")
            continue
        
        russian_text = clean_russian_words_only(text)
        if len(russian_text.split()) < 5:
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='TOO SHORT').add(db)
            results.append("Text contains too few Russian words. Please provide a text with at least 5 Russian words.")
            continue
        
        text = clean_text(text)

        if not is_text_analyzable(text):
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='NOT MEANINGFUL').add(db)
            results.append("The text is not meaningful. Please provide a meaningful text.")
            continue
        
        else:
            now = datetime.now()

            linguistic_report = create_linguistic_report(text)

            level = choice([1, 2, 3, 4, 5, 6])
            level_cefr = level_to_cefr(level)
            
            level_id = LevelsCRUD(level=level_cefr).find(db)

            TextsCRUD(
                current_user.id,
                text=text,  
                linguistic_report=linguistic_report,
                level_id=str(level_id),
                is_from_csv=True,
                analyzed_at=now.strftime("%Y-%m-%d %H:%M:%S")
            ).add(db)

            results.append(level_cefr)

    df['results'] = results
    df.to_csv('data.csv', index=False, header=False)
    return FileResponse(path='data.csv', filename='results.csv', media_type='multipart/form-data')


@app.post("/history")
def history(req: HistoryRequest, db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    query = db.query(
        Texts.text,
        Levels.level,
        Texts.analyzed_at
    ).join(Levels, Texts.level_id == Levels.id).join(Users, Texts.user_id == current_user.id)

    if req.levels is not None:
        query = query.filter(Levels.level.in_(req.levels))

    if req.substring is not None:
        text = req.substring
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        query = query.filter(Texts.text.ilike(f"%{text}%"))

    rows = query.all()

    if req.sort_by == "analyzed_at_asc":
        rows.sort(key=lambda x: x.analyzed_at)
    elif req.sort_by == "analyzed_at_desc":
        rows.sort(key=lambda x: x.analyzed_at, reverse=True)
    elif req.sort_by == "text_asc":
        rows.sort(key=lambda x: x.text)
    elif req.sort_by == "text_desc":
        rows.sort(key=lambda x: x.text, reverse=True)

    history = [{"text": r.text, "level": r.level, "analyzed_at": r.analyzed_at} for r in rows]
    return {"history": history}






        



    
