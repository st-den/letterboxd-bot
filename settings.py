import os

from dotenv import load_dotenv


def add_user(user):
    users.append(user)
    save_users()


def remove_user(user):
    users.remove(user)
    save_users()


def load_users():
    global users
    users = [line.rstrip() for line in open(users_file)]


def save_users():
    open(users_file, "w").write("\n".join(users))


users_file = "users.txt"
users = []
load_users()

load_dotenv("prod.env")
session = os.getenv("SESSION")
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
phone_number = os.getenv("PHONE_NUMBER")
chat_id = int(os.getenv("CHAT_ID"))
