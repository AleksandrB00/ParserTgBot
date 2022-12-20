from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from settings import config
from .models import Base, User, BlockedUser

engine = create_engine(config.DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def add_user(tg_id, username):
    session = Session()
    user = session.query(User).filter(User.tg_id == tg_id).first()
    if user is None:
        new_user = User(tg_id=tg_id, username=username)
        session.add(new_user)
        session.commit()
        return 1
    else:
        return -1

def check_premium(tg_id):
    session = Session()
    user = session.query(User).filter(User.tg_id == tg_id).first()
    if user.premium == True:
        return 1
    else:
        return -1

def get_all_users():
    session = Session()
    users = session.query(User).all()
    return users

def check_admin(tg_id):
    session = Session()
    user = session.query(User).filter(User.tg_id == tg_id).first()
    if user.admin == True:
        return 1
    else:
        return -1

def get_admins():
    session = Session()
    users = session.query(User).filter_by(admin=True).all()
    return users

def add_blocked_users(tg_id, username):
    session = Session()
    if check_blocked(tg_id) == 1:
        new_user = BlockedUser(tg_id=tg_id, username=username)
        session.add(new_user)
        session.commit()

def get_stat():
    session = Session()
    users = session.query(User).count()
    blocked = session.query(BlockedUser).count()
    return [users, blocked]

def check_blocked(tg_id):
    session = Session()
    user = session.query(BlockedUser).filter_by(tg_id=tg_id).first()
    if user == None:
        return 1
    else:
        return -1

def delete_from_blocked(tg_id):
    session = Session()
    user = session.query(BlockedUser).filter_by(tg_id=tg_id).first()
    session.delete(user)
    session.commit()