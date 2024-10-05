import os

from dotenv import load_dotenv

users_file = "users.txt"
load_dotenv("prod.env")


def add_user(user: str) -> None:
    users.append(user)
    save_users()


def remove_user(user) -> None:
    users.remove(user)
    save_users()


def load_users(users_file: str = users_file) -> list[str]:
    with open(users_file) as f:
        return [line.rstrip() for line in f]


def save_users(users_file: str = users_file) -> None:
    global users
    with open(users_file, "w") as f:
        f.write("\n".join(users))


users = load_users()
session = os.getenv("SESSION")
api_id = int(os.getenv("API_ID"))  # type: ignore
api_hash = os.getenv("API_HASH")
phone_number = os.getenv("PHONE_NUMBER")
chat_id = int(os.getenv("CHAT_ID"))  # type: ignore
