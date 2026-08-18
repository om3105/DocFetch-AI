"""
MongoDB client initialization with fast timeout.
"""

import os

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "adaptive_rag")

client = AsyncIOMotorClient(
    MONGO_URL,
    tlsCAFile=certifi.where(),
)
db = client[DB_NAME]
