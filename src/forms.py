
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo


class LoginForm(FlaskForm):
    email = StringField(
        'Email',
        render_kw={"placeholder": "Введите email"},
        validators=[DataRequired(), Email()]
    )
    password = PasswordField(
        'Пароль',
        render_kw={"placeholder": "Введите пароль"},
        validators=[DataRequired()]
    )
    submit = SubmitField('Войти')


class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
