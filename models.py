from datetime import datetime, timedelta

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

MAX_LOAN_AMOUNT = 500.0
LOAN_INTEREST_RATE = 0.20  # flat 20% one-time interest
REPAYMENT_PERIOD_DAYS = 30
ACTIVE_LOAN_STATUSES = ("pending", "approved")

TOTAL_BEDS = 12
ADMIN_EMAILS = frozenset({"kyeikofi@gmail.com", "fkyei4life@gmail.com"})


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    program = db.Column(db.String(120))
    room_number = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)

    loans = db.relationship("Loan", backref="student", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    interest_rate = db.Column(db.Float, nullable=False, default=LOAN_INTEREST_RATE)
    purpose = db.Column(db.String(255))
    status = db.Column(db.String(20), nullable=False, default="pending")
    date_applied = db.Column(db.DateTime, default=datetime.utcnow)
    date_decided = db.Column(db.DateTime)
    due_date = db.Column(db.DateTime)

    @property
    def interest_amount(self):
        return round(self.amount * self.interest_rate, 2)

    @property
    def total_repayable(self):
        return round(self.amount + self.interest_amount, 2)

    @property
    def is_overdue(self):
        return self.status == "approved" and self.due_date is not None and datetime.utcnow() > self.due_date

    @property
    def days_remaining(self):
        if self.status != "approved" or self.due_date is None:
            return None
        return (self.due_date.date() - datetime.utcnow().date()).days

    def mark_approved(self):
        self.status = "approved"
        self.date_decided = datetime.utcnow()
        self.due_date = datetime.utcnow() + timedelta(days=REPAYMENT_PERIOD_DAYS)
