from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import Text, UniqueConstraint, Numeric

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(Text, nullable=False)

    accounts = db.relationship('Account', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"

class Account(db.Model):
    __tablename__ = 'account'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    account_id = db.Column(db.String(100), nullable=False)  # TrueLayer ID
    account_name = db.Column(db.String(100))
    bank_name = db.Column(db.String(100))
    last4 = db.Column(db.String(4))
    balance = db.Column(Numeric(12, 2), default=0.0)

    transactions = db.relationship('Transaction', backref='account', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('user_id', 'account_id', name='uq_user_account'),
    )

    def __repr__(self):
        return f"<Account {self.account_name} ({self.last4})>"

class Transaction(db.Model):
    __tablename__ = 'transaction'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(Numeric(12, 2), nullable=False)
    description = db.Column(db.String(255))
    category = db.Column(db.String(50))

    def __repr__(self):
        return f"<Transaction {self.amount} on {self.date}>"
