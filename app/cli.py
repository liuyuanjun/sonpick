"""命令行工具入口。

重置管理员密码：
    docker exec -it sonpick python -m app.cli reset-password
"""
import getpass
import sys

from app.database import SessionLocal, init_db
from app.models import User
from app.security import hash_password


def reset_password() -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).first()
        if not user:
            print("数据库中尚无管理员账户，请通过 Web 界面完成首次设置。")
            return
        pwd = getpass.getpass("请输入新密码（至少 6 位）: ")
        if len(pwd) < 6:
            print("密码至少 6 位，已取消。")
            sys.exit(1)
        pwd2 = getpass.getpass("再次输入以确认: ")
        if pwd != pwd2:
            print("两次输入不一致，已取消。")
            sys.exit(1)
        user.password_hash = hash_password(pwd)
        db.commit()
        print("管理员密码已重置。")
    finally:
        db.close()


COMMANDS = {
    "reset-password": reset_password,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"用法: python -m app.cli <{'|'.join(COMMANDS)}>")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
