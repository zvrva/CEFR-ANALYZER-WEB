import os
from pathlib import Path

import re
import pandas as pd
from random import choice
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Depends
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session


from datetime import datetime

from db import get_db

from fastapi.security import OAuth2PasswordRequestForm

if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(Path(__file__).resolve().parent / ".hf")


from db import get_db

from schemas import HistoryRequest, RegisterRequest, LoginRequest
from utils import clean_russian_words_only, clean_text, create_linguistic_report, level_to_cefr, is_text_meaningful, is_text_analyzable, validate_password_complexity, get_current_user, create_access_token, verify_password, hash_password, TextClassifierService
from models import LevelsCRUD, Texts, Levels, ErrorsCRUD, TextsCRUD, UsersCRUD, Users

app = FastAPI()
app.mount("/frontend", StaticFiles(directory=str(Path(__file__).resolve().parent / "frontend")), name="frontend")




classifier = None
@app.on_event("startup")
def load_model():
    global classifier
    classifier = TextClassifierService("models/rubert_sber.pt")
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
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form_data.username
    password = form_data.password

    user = UsersCRUD(email=email).find(db)

    if not user:
        return {'error': 'There is no user with this email.'}

    hashed_password = user.hash_password
    if not verify_password(password, hashed_password):
        return {'error': 'Wrong password.'}

    access_token = create_access_token(user.id)

    return {"access_token": access_token, "token_type": "bearer"}








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

    print(f"Linguistic report: {linguistic_report}")

    level_cefr = classifier.predict(text)
    
    level_id = LevelsCRUD(level=level_cefr).find(db)

    print(level_id, type(level_id))

    TextsCRUD(
        user_id=str(current_user.id),
        text=text,
        linguistic_report=linguistic_report,
        level_id=str(level_id),
        is_from_csv=False,
        analyzed_at=now.strftime("%Y-%m-%d %H:%M:%S")
    ).add(db)


    return {
        "warning": "TEXT MAY BE NOT MEANINGFUL. RESULTS MAY BE INACCURATE." if not is_text_meaningful(text) else None,
        "level": level_cefr,
        "linguistic_report": linguistic_report
    }

    
@app.post("/upload")
def upload(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: Users = Depends(get_current_user)):
    df = pd.read_csv(file.file, encoding='utf-8', header=None)
    
    file.file.close()

    results = []
    warnings = []

    for text in df[0]:

        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        if len(text.split()) < 5:
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='TOO SHORT').add(db)
            results.append("Text is too short. Please provide a text with at least 5 words.")
            warnings.append(" ")
            continue
        
        if len(text.split()) > 512:
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='TOO LONG').add(db)
            results.append("Text is too long. Please provide a text with no more than 512 words.")
            warnings.append(" ")
            continue
        
        russian_text = clean_russian_words_only(text)
        if len(russian_text.split()) < 5:
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='TOO SHORT').add(db)
            results.append("Text contains too few Russian words. Please provide a text with at least 5 Russian words.")
            warnings.append(" ")
            continue
        
        text = clean_text(text)

        if not is_text_analyzable(text):
            errors = ErrorsCRUD(text=text).find(db)
            if not errors:
                ErrorsCRUD(text=text, description='NOT MEANINGFUL').add(db)
            results.append("The text is not meaningful. Please provide a meaningful text.")
            warnings.append(" ")
            continue
        
        else:
            now = datetime.now()

            linguistic_report = create_linguistic_report(text)

            level = choice([1, 2, 3, 4, 5, 6])
            level_cefr = level_to_cefr(level)
            
            level_id = LevelsCRUD(level=level_cefr).find(db)

            TextsCRUD(
                user_id=str(current_user.id),
                text=text,  
                linguistic_report=linguistic_report,
                level_id=str(level_id),
                is_from_csv=True,
                analyzed_at=now.strftime("%Y-%m-%d %H:%M:%S")
            ).add(db)

            results.append(level_cefr)
            if not is_text_meaningful(text):
                warnings.append("TEXT MAY BE NOT MEANINGFUL. RESULTS MAY BE INACCURATE.")
            else:
                warnings.append(" ")

    df['results'] = results
    df['warnings'] = warnings
    df.to_csv('results.csv', index=False, header=False)
    return FileResponse(path='results.csv', filename='results.csv', media_type='multipart/form-data')


CEFR_LEVEL_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

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

    level_rank = {level: index for index, level in enumerate(CEFR_LEVEL_ORDER)}
    if req.sort_by == "analyzed_at_asc":
        rows.sort(key=lambda x: x.analyzed_at)
    elif req.sort_by == "analyzed_at_desc":
        rows.sort(key=lambda x: x.analyzed_at, reverse=True)
    elif req.sort_by == "text_asc":
        rows.sort(key=lambda x: x.text)
    elif req.sort_by == "text_desc":
        rows.sort(key=lambda x: x.text, reverse=True)
    elif req.sort_by == "level_asc":
        rows.sort(key=lambda x: level_rank.get(x.level, len(level_rank)))
    elif req.sort_by == "level_desc":
        rows.sort(key=lambda x: level_rank.get(x.level, len(level_rank)), reverse=True)

    history = [{"text": r.text, "level": r.level, "analyzed_at": r.analyzed_at} for r in rows]
    return {"history": history}


@app.get("/", response_class=FileResponse)
def get_root():
    return FileResponse(str(Path(__file__).resolve().parent / "frontend" / "index.html"))


@app.post("/register")
def get_register_page():
    return RedirectResponse(url="/analyze")


@app.post("/login", response_class=FileResponse)
def get_login_page():
    return FileResponse(str(Path(__file__).resolve().parent / "frontend" / "login.html"))


@app.post("/analyze", response_class=FileResponse)
def get_analyze_page():
    return FileResponse(str(Path(__file__).resolve().parent / "frontend" / "analyze.html"))


@app.post("/upload", response_class=FileResponse)
def get_upload_page():
    return FileResponse(str(Path(__file__).resolve().parent / "frontend" / "upload.html"))


@app.post("/history", response_class=FileResponse)
def get_history_page():
    return FileResponse(str(Path(__file__).resolve().parent / "frontend" / "history.html"))




        



    
