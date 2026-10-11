"""Caches the bot's own identity (fetched once at startup) for mention checks."""
username: str = None
user_id: int = None


def set_identity(uname: str, uid: int):
    global username, user_id
    username = uname
    user_id = uid
