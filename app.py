import csv
import io
import os
import threading
from datetime import datetime
from functools import wraps

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_mail import Mail, Message
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import inspect, text

from extensions import db
from forms import (
    AdminAccessForm,
    AdminStudentEditForm,
    ChangePasswordForm,
    ForgotPasswordForm,
    LoanForm,
    LoginForm,
    PaymentForm,
    ProfileForm,
    RegisterForm,
    ResetPasswordForm,
)
from models import (
    ACTIVE_LOAN_STATUSES,
    ADMIN_EMAILS,
    CHECKOUT_PAYMENT_AMOUNT,
    LOAN_INTEREST_RATE,
    MAX_LOAN_AMOUNT,
    PAYMENT_ACTIVE_STATUSES,
    PAYMENT_MOMO_NUMBER,
    REPAYMENT_PERIOD_DAYS,
    TOTAL_BEDS,
    Loan,
    Payment,
    User,
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

database_url = os.environ.get("DATABASE_URL", "sqlite:///olive_gate.db")
if database_url.startswith("postgres://"):
    # Render (and some other providers) hand out the legacy "postgres://" scheme,
    # but SQLAlchemy 1.4+ requires "postgresql://".
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])

db.init_app(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

limiter = Limiter(get_remote_address, app=app, default_limits=[])

NOTIFY_RECIPIENTS = ["fkyei4life@gmail.com", "kyeikofi@gmail.com"]


def send_email_async(subject, recipients, body):
    """Fire-and-forget email so requests never wait on SMTP."""
    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        app.logger.warning("MAIL_USERNAME/MAIL_PASSWORD not set; skipping email: %s", subject)
        return

    def _send():
        with app.app_context():
            try:
                mail.send(Message(subject=subject, recipients=recipients, body=body))
            except Exception:
                app.logger.exception("Failed to send email: %s", subject)

    threading.Thread(target=_send, daemon=True).start()


def notify(subject, body):
    send_email_async(subject, NOTIFY_RECIPIENTS, body)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return wrapper


@app.route("/")
def index():
    occupied_beds, beds_available = _bed_stats()
    return render_template(
        "index.html",
        max_amount=MAX_LOAN_AMOUNT,
        rate_pct=int(LOAN_INTEREST_RATE * 100),
        repayment_days=REPAYMENT_PERIOD_DAYS,
        beds_available=beds_available,
        total_beds=TOTAL_BEDS,
    )


def _bed_stats():
    occupied = User.query.filter_by(role="student").count()
    return occupied, max(TOTAL_BEDS - occupied, 0)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = RegisterForm()
    occupied_beds, beds_available = _bed_stats()

    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        is_admin_signup = email in ADMIN_EMAILS

        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "danger")
            return render_template("register.html", form=form, beds_available=beds_available, total_beds=TOTAL_BEDS)

        if not is_admin_signup and beds_available <= 0:
            flash("Sorry, all 12 beds are currently full. Registration is closed for now.", "danger")
            return render_template("register.html", form=form, beds_available=0, total_beds=TOTAL_BEDS)

        user = User(
            full_name=form.full_name.data.strip(),
            email=email,
            phone=form.phone.data.strip(),
            program=form.program.data.strip(),
            room_number=form.room_number.data.strip(),
            check_in_date=form.check_in_date.data,
            check_out_date=form.check_out_date.data,
            role="admin" if is_admin_signup else "student",
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        if is_admin_signup:
            notify(
                "New Admin Account Created - Olive Gate Hostel",
                "An admin account was just created at Olive Gate Hostel.\n\n"
                f"Name: {user.full_name}\n"
                f"Email: {user.email}\n"
                f"Created On: {user.date_registered.strftime('%d %b %Y, %I:%M %p')}\n",
            )
            flash("Admin account created. Please log in.", "success")
        else:
            notify(
                "New Room Application - Olive Gate Hostel",
                "A new student has applied for a room at Olive Gate Hostel.\n\n"
                f"Name: {user.full_name}\n"
                f"Email: {user.email}\n"
                f"Phone: {user.phone}\n"
                f"Program: {user.program}\n"
                f"Room Number: {user.room_number or 'Not specified'}\n"
                f"Check-in: {user.check_in_date.strftime('%d %b %Y')}\n"
                f"Check-out: {user.check_out_date.strftime('%d %b %Y')}\n"
                f"Registered On: {user.date_registered.strftime('%d %b %Y, %I:%M %p')}\n"
                f"Beds Occupied Now: {occupied_beds + 1} / {TOTAL_BEDS}\n",
            )
            flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form=form, beds_available=beds_available, total_beds=TOTAL_BEDS)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("8 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash(f"Welcome back, {user.full_name.split()[0]}!", "success")
            return redirect(url_for("admin_dashboard") if user.is_admin else url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html", form=form)


def _reset_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])


@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        user = User.query.filter_by(email=email).first()
        if user:
            token = _reset_serializer().dumps(email, salt="password-reset")
            reset_url = url_for("reset_password", token=token, _external=True)
            send_email_async(
                "Reset Your Password - Olive Gate Hostel",
                [user.email],
                "We received a request to reset your Olive Gate Hostel password.\n\n"
                f"Click this link to set a new password (valid for 1 hour):\n{reset_url}\n\n"
                "If you didn't request this, you can safely ignore this email.",
            )
        flash("If that email is registered, a password reset link has been sent to it.", "info")
        return redirect(url_for("login"))
    return render_template("forgot_password.html", form=form)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def reset_password(token):
    try:
        email = _reset_serializer().loads(token, salt="password-reset", max_age=3600)
    except (BadSignature, SignatureExpired):
        flash("This password reset link is invalid or has expired.", "danger")
        return redirect(url_for("forgot_password"))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("This password reset link is invalid.", "danger")
        return redirect(url_for("forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        db.session.commit()
        flash("Your password has been reset. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", form=form)


@app.route("/admin-login", methods=["GET", "POST"])
@limiter.limit("8 per minute", methods=["POST"])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard") if current_user.is_admin else url_for("dashboard"))
    form = AdminAccessForm()
    access_code = os.environ.get("ADMIN_ACCESS_CODE")
    if form.validate_on_submit():
        if not access_code:
            flash("Admin access isn't configured yet. Contact the site owner.", "danger")
        elif form.admin_password.data != access_code:
            flash("Incorrect admin password.", "danger")
        else:
            email = form.email.data.lower().strip()
            user = User.query.filter_by(email=email).first()
            if user:
                if not user.is_admin:
                    user.role = "admin"
                    db.session.commit()
            else:
                user = User(full_name=form.full_name.data.strip(), email=email, role="admin")
                user.set_password(access_code)
                db.session.add(user)
                db.session.commit()
            login_user(user)
            flash(f"Welcome, {user.full_name.split()[0]}! You're logged in as admin.", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


def _has_active_loan(user):
    return Loan.query.filter(Loan.student_id == user.id, Loan.status.in_(ACTIVE_LOAN_STATUSES)).first()


def _latest_payment(user):
    return Payment.query.filter_by(student_id=user.id).order_by(Payment.date_submitted.desc()).first()


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    loans = Loan.query.filter_by(student_id=current_user.id).order_by(Loan.date_applied.desc()).all()
    return render_template(
        "dashboard.html",
        loans=loans,
        max_amount=MAX_LOAN_AMOUNT,
        rate_pct=int(LOAN_INTEREST_RATE * 100),
        has_active_loan=bool(_has_active_loan(current_user)),
        repayment_days=REPAYMENT_PERIOD_DAYS,
        latest_payment=_latest_payment(current_user),
        checkout_amount=CHECKOUT_PAYMENT_AMOUNT,
        payment_number=PAYMENT_MOMO_NUMBER,
    )


@app.route("/loans/apply", methods=["GET", "POST"])
@login_required
def apply_loan():
    if current_user.is_admin:
        abort(403)
    if _has_active_loan(current_user):
        flash("You already have a pending or approved loan. Apply again once it's resolved.", "warning")
        return redirect(url_for("dashboard"))
    form = LoanForm()
    if form.validate_on_submit():
        loan = Loan(
            student_id=current_user.id,
            amount=form.amount.data,
            interest_rate=LOAN_INTEREST_RATE,
            purpose=form.purpose.data.strip(),
        )
        db.session.add(loan)
        db.session.commit()
        notify(
            "New Loan Application - Olive Gate Hostel",
            "A new loan application has been submitted at Olive Gate Hostel.\n\n"
            f"Student: {current_user.full_name}\n"
            f"Email: {current_user.email}\n"
            f"Phone: {current_user.phone}\n"
            f"Amount Requested: GHc {loan.amount:.2f}\n"
            f"Interest ({int(loan.interest_rate * 100)}%): GHc {loan.interest_amount:.2f}\n"
            f"Total Repayable: GHc {loan.total_repayable:.2f}\n"
            f"Purpose: {loan.purpose}\n"
            f"Applied On: {loan.date_applied.strftime('%d %b %Y, %I:%M %p')}\n",
        )
        flash("Loan application submitted successfully.", "success")
        return redirect(url_for("dashboard"))
    return render_template(
        "apply_loan.html",
        form=form,
        max_amount=MAX_LOAN_AMOUNT,
        rate_pct=int(LOAN_INTEREST_RATE * 100),
        repayment_days=REPAYMENT_PERIOD_DAYS,
    )


@app.route("/payment/submit", methods=["GET", "POST"])
@login_required
def submit_payment():
    if current_user.is_admin:
        abort(403)
    latest = _latest_payment(current_user)
    if latest and latest.status in PAYMENT_ACTIVE_STATUSES:
        flash("You already have a payment submission on record.", "info")
        return redirect(url_for("dashboard"))
    form = PaymentForm()
    if form.validate_on_submit():
        payment = Payment(
            student_id=current_user.id,
            amount=CHECKOUT_PAYMENT_AMOUNT,
            transaction_reference=form.transaction_reference.data.strip(),
        )
        db.session.add(payment)
        db.session.commit()
        notify(
            "New Checkout Payment Submitted - Olive Gate Hostel",
            "A student has submitted a checkout payment for review.\n\n"
            f"Student: {current_user.full_name}\n"
            f"Email: {current_user.email}\n"
            f"Amount: GHc {payment.amount:.2f}\n"
            f"Transaction Reference: {payment.transaction_reference}\n"
            f"Submitted On: {payment.date_submitted.strftime('%d %b %Y, %I:%M %p')}\n",
        )
        flash("Payment confirmation submitted. The admin will verify and approve it.", "success")
        return redirect(url_for("dashboard"))
    return render_template(
        "submit_payment.html", form=form, amount=CHECKOUT_PAYMENT_AMOUNT, payment_number=PAYMENT_MOMO_NUMBER
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if current_user.is_admin:
        abort(403)
    profile_form = ProfileForm(prefix="profile", obj=current_user)
    password_form = ChangePasswordForm(prefix="pwd")

    if profile_form.submit.data and profile_form.validate_on_submit():
        current_user.full_name = profile_form.full_name.data.strip()
        current_user.phone = profile_form.phone.data.strip()
        current_user.program = profile_form.program.data.strip()
        current_user.room_number = profile_form.room_number.data.strip()
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))

    if password_form.submit.data and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("profile"))

    return render_template("profile.html", profile_form=profile_form, password_form=password_form)


@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    student_query = request.args.get("q", "").strip()
    loan_status_filter = request.args.get("status", "").strip()

    students_q = User.query.filter_by(role="student")
    if student_query:
        like = f"%{student_query}%"
        students_q = students_q.filter(db.or_(User.full_name.ilike(like), User.email.ilike(like)))
    students = students_q.order_by(User.date_registered.desc()).all()

    all_loans = Loan.query.order_by(Loan.date_applied.desc()).all()
    loans = all_loans
    if loan_status_filter:
        loans = [loan for loan in loans if loan.status == loan_status_filter]

    pending_count = sum(1 for loan in all_loans if loan.status == "pending")
    total_lent = sum(loan.amount for loan in all_loans if loan.status in ("approved", "repaid"))
    outstanding_balance = sum(loan.total_repayable for loan in all_loans if loan.status == "approved")
    occupied_beds, beds_available = _bed_stats()

    payments = Payment.query.order_by(Payment.date_submitted.desc()).all()
    pending_payments_count = sum(1 for p in payments if p.status == "pending")

    return render_template(
        "admin_dashboard.html",
        students=students,
        loans=loans,
        pending_count=pending_count,
        total_lent=total_lent,
        outstanding_balance=outstanding_balance,
        student_query=student_query,
        loan_status_filter=loan_status_filter,
        total_student_count=occupied_beds,
        occupied_beds=occupied_beds,
        beds_available=beds_available,
        total_beds=TOTAL_BEDS,
        payments=payments,
        pending_payments_count=pending_payments_count,
    )


@app.route("/admin/loans/<int:loan_id>/<action>", methods=["POST"])
@login_required
@admin_required
def decide_loan(loan_id, action):
    if action not in ("approve", "reject", "repaid"):
        abort(400)
    loan = Loan.query.get_or_404(loan_id)
    if action == "approve":
        loan.mark_approved()
    else:
        loan.status = "rejected" if action == "reject" else "repaid"
        loan.date_decided = datetime.utcnow()
    db.session.commit()
    flash(f"Loan #{loan.id} marked as {loan.status}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/payments/<int:payment_id>/<action>", methods=["POST"])
@login_required
@admin_required
def decide_payment(payment_id, action):
    if action not in ("approve", "reject"):
        abort(400)
    payment = Payment.query.get_or_404(payment_id)
    payment.status = "approved" if action == "approve" else "rejected"
    payment.date_decided = datetime.utcnow()
    db.session.commit()
    flash(f"Payment #{payment.id} marked as {payment.status}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/students/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    form = AdminStudentEditForm(obj=student)
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        existing = User.query.filter(User.email == email, User.id != student.id).first()
        if existing:
            flash("Another account already uses that email.", "danger")
        else:
            student.full_name = form.full_name.data.strip()
            student.email = email
            student.phone = form.phone.data.strip()
            student.program = form.program.data.strip()
            student.room_number = form.room_number.data.strip()
            student.check_in_date = form.check_in_date.data
            student.check_out_date = form.check_out_date.data
            if form.new_password.data:
                student.set_password(form.new_password.data)
            db.session.commit()
            flash("Student record updated.", "success")
            return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit_student.html", form=form, student=student)


@app.route("/admin/students/<int:student_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_student(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    db.session.delete(student)
    db.session.commit()
    flash(f"{student.full_name} and their loan records have been deleted.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export/students.csv")
@login_required
@admin_required
def export_students_csv():
    students = User.query.filter_by(role="student").order_by(User.date_registered.desc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Full Name", "Email", "Phone", "Program", "Room Number", "Check-in", "Check-out", "Registered On"]
    )
    for student in students:
        writer.writerow(
            [
                student.full_name,
                student.email,
                student.phone,
                student.program,
                student.room_number or "",
                student.check_in_date.strftime("%Y-%m-%d") if student.check_in_date else "",
                student.check_out_date.strftime("%Y-%m-%d") if student.check_out_date else "",
                student.date_registered.strftime("%Y-%m-%d"),
            ]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=olive_gate_students.csv"},
    )


@app.route("/admin/export/loans.csv")
@login_required
@admin_required
def export_loans_csv():
    loans = Loan.query.order_by(Loan.date_applied.desc()).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Loan ID", "Student", "Amount", "Interest", "Total Repayable", "Purpose", "Status", "Applied On", "Due Date"]
    )
    for loan in loans:
        writer.writerow(
            [
                loan.id,
                loan.student.full_name,
                f"{loan.amount:.2f}",
                f"{loan.interest_amount:.2f}",
                f"{loan.total_repayable:.2f}",
                loan.purpose,
                loan.status,
                loan.date_applied.strftime("%Y-%m-%d"),
                loan.due_date.strftime("%Y-%m-%d") if loan.due_date else "",
            ]
        )
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=olive_gate_loans.csv"},
    )


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="You don't have permission to view this page."), 403


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(429)
def rate_limited(_e):
    return render_template("error.html", code=429, message="Too many attempts. Please wait a moment and try again."), 429


def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return
    admin_email = admin_email.lower().strip()
    if User.query.filter_by(email=admin_email).first():
        return
    admin = User(full_name="Hostel Administrator", email=admin_email, role="admin")
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()


def run_lightweight_migrations():
    """Add newly-introduced columns to a pre-existing 'user' table.

    db.create_all() only creates missing tables; it never alters an
    existing table's columns, so new User fields need to be patched in
    by hand on databases that predate them.
    """
    inspector = inspect(db.engine)
    if "user" not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns("user")}
    missing = [
        name for name in ("check_in_date", "check_out_date") if name not in existing_columns
    ]
    if not missing:
        return
    with db.engine.begin() as conn:
        for name in missing:
            conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {name} DATE'))


with app.app_context():
    db.create_all()
    run_lightweight_migrations()
    seed_admin()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
