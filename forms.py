from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange, Optional, Regexp, ValidationError

from models import MAX_LOAN_AMOUNT

PHONE_VALIDATOR = Regexp(r"^[0-9+\-\s]{7,20}$", message="Enter a valid phone number.")


class RegisterForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField("Phone Number", validators=[DataRequired(), PHONE_VALIDATOR])
    program = StringField("Program / Course of Study", validators=[DataRequired(), Length(max=120)])
    room_number = StringField("Preferred Room Number (optional)", validators=[Length(max=20)])
    check_in_date = DateField("Check-in Date", validators=[DataRequired()])
    check_out_date = DateField("Check-out Date", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")]
    )
    submit = SubmitField("Register")

    def validate_check_out_date(self, field):
        if self.check_in_date.data and field.data and field.data <= self.check_in_date.data:
            raise ValidationError("Check-out date must be after the check-in date.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


class AdminAccessForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    admin_password = PasswordField("Admin Password", validators=[DataRequired()])
    submit = SubmitField("Enter Admin Dashboard")


class LoanForm(FlaskForm):
    amount = FloatField(
        "Loan Amount (GHc)",
        validators=[DataRequired(), NumberRange(min=1, max=MAX_LOAN_AMOUNT, message=f"Amount must be between GHc 1 and GHc {MAX_LOAN_AMOUNT:.0f}.")],
    )
    purpose = TextAreaField("Purpose of Loan", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Submit Application")


class ProfileForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    phone = StringField("Phone Number", validators=[DataRequired(), PHONE_VALIDATOR])
    program = StringField("Program / Course of Study", validators=[DataRequired(), Length(max=120)])
    room_number = StringField("Room Number (optional)", validators=[Length(max=20)])
    submit = SubmitField("Save Changes")


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current Password", validators=[DataRequired()])
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6)])
    confirm_new_password = PasswordField(
        "Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")]
    )
    submit = SubmitField("Change Password")


class AdminStudentEditForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField("Phone Number", validators=[DataRequired(), PHONE_VALIDATOR])
    program = StringField("Program / Course of Study", validators=[DataRequired(), Length(max=120)])
    room_number = StringField("Room Number (optional)", validators=[Length(max=20)])
    check_in_date = DateField("Check-in Date", validators=[Optional()])
    check_out_date = DateField("Check-out Date", validators=[Optional()])
    new_password = PasswordField(
        "Reset Password (optional)", validators=[Optional(), Length(min=6, message="New password must be at least 6 characters.")]
    )
    submit = SubmitField("Save Changes")

    def validate_check_out_date(self, field):
        if self.check_in_date.data and field.data and field.data <= self.check_in_date.data:
            raise ValidationError("Check-out date must be after the check-in date.")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Send Reset Link")


class ResetPasswordForm(FlaskForm):
    new_password = PasswordField("New Password", validators=[DataRequired(), Length(min=6)])
    confirm_new_password = PasswordField(
        "Confirm New Password", validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")]
    )
    submit = SubmitField("Reset Password")


class PaymentForm(FlaskForm):
    transaction_reference = StringField(
        "Mobile Money Transaction Reference",
        validators=[DataRequired(), Length(max=120)],
    )
    submit = SubmitField("Submit Payment Confirmation")
