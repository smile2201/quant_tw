"""
auth/user_manager.py
帳號管理核心模組
- 帳號存在 data/users.json
- 密碼用 SHA-256 + salt hash 儲存，不明文
- 角色：admin（管理員）/ viewer（瀏覽者）
"""
import os, json, hashlib, secrets
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
USERS_FILE   = PROJECT_ROOT / "data" / "users.json"

ROLES = {
    "admin":  "管理員",
    "viewer": "瀏覽者",
}

ROLE_PERMISSIONS = {
    "admin":  ["screener", "backtest", "data", "settings", "scripts", "logs", "users"],
    "viewer": ["screener", "backtest"],
}


def _hash_password(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return hashed, salt


def _verify_password(password: str, hashed: str, salt: str) -> bool:
    h, _ = _hash_password(password, salt)
    return h == hashed


def _load() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return {}


def _save(users: dict):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2))


def init_default_admin():
    """首次執行建立預設管理員：admin / admin1234"""
    users = _load()
    if users:
        return
    hashed, salt = _hash_password("admin1234")
    users["admin"] = {
        "username":   "admin",
        "role":       "admin",
        "hashed":     hashed,
        "salt":       salt,
        "active":     True,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
    }
    _save(users)


def verify(username: str, password: str):
    if not username or not password:
        return None
    users = _load()
    user  = users.get(username)
    if not user or not user.get("active", True):
        return None
    if not _verify_password(password, user["hashed"], user["salt"]):
        return None
    user["last_login"] = datetime.now().isoformat()
    users[username] = user
    _save(users)
    return {"username": username, "role": user["role"]}


def list_users() -> list:
    users = _load()
    result = []
    for uname, info in users.items():
        result.append({
            "帳號":     uname,
            "角色":     ROLES.get(info.get("role", "viewer"), "瀏覽者"),
            "role":     info.get("role", "viewer"),
            "狀態":     "✅ 啟用" if info.get("active", True) else "🔴 停用",
            "active":   info.get("active", True),
            "建立時間": info.get("created_at", "")[:10],
            "最後登入": (info.get("last_login") or "從未登入")[:16].replace("T", " "),
        })
    return result


def add_user(username: str, password: str, role: str = "viewer"):
    username = username.strip()
    if not username or len(username) < 3:
        return False, "帳號至少 3 個字元"
    if len(password) < 6:
        return False, "密碼至少 6 個字元"
    if role not in ROLES:
        return False, f"角色無效：{role}"
    users = _load()
    if username in users:
        return False, f"帳號「{username}」已存在"
    hashed, salt = _hash_password(password)
    users[username] = {
        "username":   username,
        "role":       role,
        "hashed":     hashed,
        "salt":       salt,
        "active":     True,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
    }
    _save(users)
    return True, f"帳號「{username}」建立成功"


def reset_password(username: str, new_password: str):
    if len(new_password) < 6:
        return False, "密碼至少 6 個字元"
    users = _load()
    if username not in users:
        return False, "帳號不存在"
    hashed, salt = _hash_password(new_password)
    users[username]["hashed"] = hashed
    users[username]["salt"]   = salt
    _save(users)
    return True, f"「{username}」密碼已重設"


def toggle_active(username: str, current_operator: str):
    if username == current_operator:
        return False, "不能停用自己的帳號"
    users = _load()
    if username not in users:
        return False, "帳號不存在"
    if users[username]["role"] == "admin":
        admins = [u for u, i in users.items() if i["role"] == "admin" and i.get("active", True)]
        if len(admins) <= 1 and users[username].get("active", True):
            return False, "不能停用唯一的管理員帳號"
    current = users[username].get("active", True)
    users[username]["active"] = not current
    _save(users)
    return True, f"帳號「{username}」已{'停用' if current else '啟用'}"


def delete_user(username: str, current_operator: str):
    if username == current_operator:
        return False, "不能刪除自己的帳號"
    users = _load()
    if username not in users:
        return False, "帳號不存在"
    if users[username]["role"] == "admin":
        admins = [u for u in users if users[u]["role"] == "admin"]
        if len(admins) <= 1:
            return False, "不能刪除唯一的管理員帳號"
    del users[username]
    _save(users)
    return True, f"帳號「{username}」已刪除"


def change_role(username: str, new_role: str, current_operator: str):
    if username == current_operator:
        return False, "不能修改自己的角色"
    if new_role not in ROLES:
        return False, f"角色無效：{new_role}"
    users = _load()
    if username not in users:
        return False, "帳號不存在"
    if users[username]["role"] == "admin" and new_role != "admin":
        admins = [u for u in users if users[u]["role"] == "admin"]
        if len(admins) <= 1:
            return False, "不能降級唯一的管理員"
    users[username]["role"] = new_role
    _save(users)
    return True, f"「{username}」角色已改為{ROLES[new_role]}"


def change_own_password(username: str, old_password: str, new_password: str):
    users = _load()
    user  = users.get(username)
    if not user:
        return False, "帳號不存在"
    if not _verify_password(old_password, user["hashed"], user["salt"]):
        return False, "舊密碼錯誤"
    if len(new_password) < 6:
        return False, "新密碼至少 6 個字元"
    if old_password == new_password:
        return False, "新密碼不能與舊密碼相同"
    hashed, salt = _hash_password(new_password)
    users[username]["hashed"] = hashed
    users[username]["salt"]   = salt
    _save(users)
    return True, "密碼修改成功"


def user_count() -> int:
    return len(_load())


def has_permission(role: str, page: str) -> bool:
    return page in ROLE_PERMISSIONS.get(role, [])
