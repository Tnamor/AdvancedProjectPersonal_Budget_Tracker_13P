from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from dotenv import load_dotenv
from src.forms import LoginForm, RegisterForm
from src.models import db, User, Account, Transaction
from src.openbanking.oauth import oauth_bp
from openbanking.client import get_accounts, get_transactions
from auth import auth_bp
from flask_migrate import Migrate
from urllib.parse import quote_plus
import sys
import os

# Добавление пути к проекту в системный путь
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Загрузка переменных окружения
load_dotenv()

# Инициализация Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_key')

# Конфигурация базы данных
password = quote_plus("rtbroman04@2")  # Заменить на безопасное хранение!
app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql://postgres:{password}@localhost:5432/personal_budget_tracker"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Инициализация расширений
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Регистрация Blueprint'ов
app.register_blueprint(oauth_bp, url_prefix="/oauth")
app.register_blueprint(auth_bp, url_prefix="/auth")


# Фильтр форматирования валюты
def format_currency(amount):
    return "${:,.2f}".format(amount)

@app.template_filter('usd')
def usd_filter(amount):
    return format_currency(amount)

# Загрузка пользователя
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# === МАРШРУТЫ ===

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Email уже зарегистрирован.", "danger")
            return redirect(url_for("register"))
        user = User(email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("dashboard"))
    return render_template("register.html", form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Неверный логин или пароль.", "danger")
    return render_template("login.html", form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    recent = (
        Transaction.query.join(Account)
        .filter(Account.user_id == current_user.id)
        .order_by(Transaction.date.desc())
        .limit(5)
        .all()
    )
    total = sum(a.balance for a in accounts)

    for acc in accounts:
        acc.formatted_balance = format_currency(acc.balance)

    balances = {
        'cash': format_currency(sum(a.balance for a in accounts if a.account_name.lower() == 'cash')),
        'debit': format_currency(sum(a.balance for a in accounts if a.account_name.lower() == 'debit')),
        'crypto': format_currency(sum(a.balance for a in accounts if a.account_name.lower() == 'crypto')),
    }

    return render_template(
        'dashboard.html',
        accounts=accounts,
        recent_transactions=recent,
        total_budget=format_currency(total),
        balances=balances
    )

@app.template_filter('usd')
def usd_filter(value):
    return "${:,.2f}".format(value)
@app.route('/account/<int:account_id>')
@login_required
def account_detail(account_id):
    account = Account.query.get_or_404(account_id)

    # Проверка владельца
    if account.user_id != current_user.id:
        flash("Нет доступа к этому аккаунту.", "danger")
        return redirect(url_for('dashboard'))

    transactions = (
        Transaction.query
        .filter_by(account_id=account.id)
        .order_by(Transaction.date.desc())
        .all()
    )

    # Подготовка данных для графика (линейный — история трат)
    chart_labels = [tx.date.strftime('%Y-%m-%d') for tx in transactions]
    chart_data = [float(tx.amount) for tx in transactions]

    # Категории трат для круговой диаграммы
    categories = (
        db.session.query(Transaction.category, db.func.sum(Transaction.amount))
        .filter_by(account_id=account.id)
        .group_by(Transaction.category)
        .all()
    )
    category_labels = [c[0] for c in categories]
    category_values = [float(c[1]) for c in categories]
    category_summary = list(zip(category_labels, category_values))

    return render_template(
        'account_detail.html',
        account=account,
        transactions=transactions,
        chart_labels=chart_labels,
        chart_data=chart_data,
        category_labels=category_labels,
        category_values=category_values,
        category_summary=category_summary
    )

@app.route('/import-transactions')
@login_required
def import_transactions():
    token = session.get("access_token")
    if not token:
        return redirect(url_for("oauth.connect_wallet"))

    try:
        for acc in get_accounts(token):
            acc_obj = Account.query.filter_by(account_id=acc['account_id'], user_id=current_user.id).first()
            if not acc_obj:
                acc_obj = Account(
                    user_id=current_user.id,
                    account_id=acc['account_id'],
                )
                db.session.add(acc_obj)
                db.session.flush()  # Гарантирует наличие acc_obj.id

            # Обновляем поля
            acc_obj.account_name = acc.get('display_name', 'Unknown')
            acc_obj.bank_name = acc.get('provider', {}).get('display_name', '')
            acc_obj.last4 = acc.get('account_number', {}).get('number', '')[-4:]
            acc_obj.balance = acc.get('balance', {}).get('current', 0.0)

            db.session.flush()

            for tx in get_transactions(acc['account_id'], token):
                try:
                    date = datetime.fromisoformat(tx.get('timestamp', '')[:19])
                except Exception:
                    continue

                # Проверка на дубликаты
                exists = Transaction.query.filter_by(
                    account_id=acc_obj.id,
                    date=date,
                    amount=tx.get('amount', {}).get('value', 0),
                    description=tx.get('description', '')
                ).first()
                if exists:
                    continue

                db.session.add(Transaction(
                    account_id=acc_obj.id,
                    date=date,
                    amount=tx.get('amount', {}).get('value', 0),
                    description=tx.get('description', ''),
                    category=tx.get('transaction_category', '')
                ))

        db.session.commit()
        flash("Импорт завершён успешно.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при импорте: {e}", "danger")

    return redirect(url_for("dashboard"))
@app.route('/connect-bank')
@login_required
def connect_bank():
    return redirect(url_for("oauth.connect_wallet"))

# Запуск
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
