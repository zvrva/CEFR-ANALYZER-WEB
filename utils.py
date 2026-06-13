import re
from collections import Counter
import pymorphy3

import os
from pathlib import Path

import re
from datetime import datetime

from fastapi import Depends

from sqlalchemy.orm import Session



import torch


if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(Path(__file__).resolve().parent / ".hf")

from transformers import AutoTokenizer, AutoModelForSequenceClassification

from datetime import datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from models import Users
from db import get_db

if "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = str(Path(__file__).resolve().parent / ".hf")






def clean_russian_words_only(text: str) -> str:
    if not isinstance(text, str):
        return ""

    text = re.sub(r'[\t\n\r]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    tokens = text.split()

    russian_words = []
    for token in tokens:
        token_clean = re.sub(r'^[^\wА-Яа-яЁё]+|[^\wА-Яа-яЁё]+$', '', token)

        if re.fullmatch(r'[А-Яа-яЁё]+', token_clean):
            russian_words.append(token_clean)

    return ' '.join(russian_words)

def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    text = re.sub(r'[\t\n\r]+', ' ', text)

    text = re.sub(r'[^A-Za-zА-Яа-яЁё0-9\s.,!?;:()\-"\'«»—\-]', '', text)

    text = re.sub(r'\s+', ' ', text).strip()

    return text

def create_linguistic_report(text: str) -> dict:
    return {
        "word_count": len(text.split()),
        "length": len(text),
    }


def level_to_cefr(level: int) -> str:
    mapping = {
        1: "A1",
        2: "A2",
        3: "B1",
        4: "B2",
        5: "C1",
        6: "C2"
    }
    return mapping.get(level, "NO")
    


def is_text_analyzable(text: str) -> bool:
    letters_and_digits = re.findall(r"[А-Яа-яЁёA-Za-z0-9]", text)
    special_symbols = re.findall(r"[^А-Яа-яЁёA-Za-z0-9\s]", text)
    print(0)

    if letters_and_digits and len(special_symbols) / len(letters_and_digits) > 0.7:
        print(1)
        return False

    english_words = re.findall(r"\b[A-Za-z]+\b", text)

    if len(english_words) / len(text.split()) > 0.3:
        print(2)
        return False
    
    if re.search(r"(.)\1{7,}", text):
        print(3)
        return False

    random_latin_tokens = [
        word for word in english_words
        if len(word) >= 6 and not re.search(r"[aeiouyAEIOUY]", word)
    ]

    if len(random_latin_tokens) >= 2:
        print(4)
        return False
    
    return True
    
def is_text_meaningful(text: str) -> bool:
    morph = pymorphy3.MorphAnalyzer()

    words = re.findall(r"\b[А-Яа-яЁё]+\b", text.lower())

    pos_tags = []
    for word in words:
        parse = morph.parse(word)[0]
        pos = parse.tag.POS
        if pos:
            pos_tags.append(pos)
    pos_counter = Counter(pos_tags)
    if pos_counter:
        _, count = pos_counter.most_common(1)[0]

        if count / len(pos_tags) > 0.8:
            return False

    has_verb = any(
        pos in ["VERB", "INFN"]
        for pos in pos_tags
    )
    if not has_verb:
        return False


    sentences = re.split(r"[.!?]+", text)
    short_sentences = [
        s for s in sentences
        if 0 < len(s.split()) <= 2
    ]
    if len(short_sentences) >= 2:
        return False

    return True


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
    

def validate_password_complexity(password: str):
    if len(password) < 8:
        return "Password must be at least 8 characters long."
        
    
    if not re.search(r"[A-Z]", password):
        return "Пароль должен содержать хотя бы одну заглавную букву"
        
    
    if not re.search(r"[a-z]", password):
        return "Пароль должен содержать хотя бы одну строчную букву"
        
    
    if not re.search(r"[0-9]", password):
        return "Password must contains at least 1 digit."
        
    
    if not re.search(r"[ !@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return "Пароль должен содержать хотя бы один специальный символ"
    

    common_sequences = ["12345678", "password", "qwertyui", "abcdefgh", "11111111", "01234567", "asdfghjk", "zxcvbnm,", "Gfhjkm02"]
    if any(seq in password.lower() for seq in common_sequences):
        return "Password is too easy."
    
    return None





ACCESS_TOKEN_EXPIRE_MINUTES=os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
SECRET_KEY=os.getenv("SECRET_KEY")
ALGORITHM=os.getenv("ALGORITHM")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить авторизацию",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    user = db.query(Users).filter(Users.id == user_id).first()

    if user is None:
        raise credentials_exception

    return user



def verify_password(password: str, hashed_password: str) -> bool:
    password_bytes = password.encode("utf-8")
    hashed_password_bytes = hashed_password.encode("utf-8")

    return bcrypt.checkpw(password_bytes, hashed_password_bytes)



def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=float(ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": str(user_id),
        "exp": expire
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token