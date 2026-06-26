import hashlib
import secrets
import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

_mongo_client = MongoClient(os.getenv("MONGO_URI"))
_users_col = _mongo_client["founderflow"]["users"]


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{pwd_hash}"


def verify_password(password: str, stored: str) -> bool:
    salt, pwd_hash = stored.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == pwd_hash


def create_user(username: str, email: str, password: str) -> dict | None:
    if _users_col.find_one({"email": email}):
        return None
    user = {
        "username": username,
        "email": email,
        "password": hash_password(password),
    }
    result = _users_col.insert_one(user)
    return {"id": str(result.inserted_id), "username": username, "email": email}


def authenticate_user(email: str, password: str) -> dict | None:
    user = _users_col.find_one({"email": email})
    if not user or not verify_password(password, user["password"]):
        return None
    return {"id": str(user["_id"]), "username": user["username"], "email": user["email"]}
