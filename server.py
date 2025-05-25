import re
from datetime import datetime
from functools import wraps

import psycopg2
from flask import Flask, session, redirect, url_for, request, render_template, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_key"

# Настройки базы данных
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "users_application"
DB_USER = "administrator"
DB_PASSWORD = "root"

# Подключение к базе данных PostgreSQL
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            client_encoding='utf8'
        )
        return conn
    except psycopg2.Error as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return None

# Проверка авторизации перед загрузкой защищённых страниц
def login_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return decorated_function

# Главная страница (редиректит на домашнюю)
@app.route('/')
def index():
    return redirect(url_for('home'))

# Домашняя страница (приветствие)
@app.route('/home')
def home():
    return render_template('home.html')

# Регистрация нового пользователя
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        errors = {}

        #  Проверка логина
        if not (username and 3 <= len(username) <= 20):
            errors['username'] = "Логин должен содержать от 3 до 20 символов"
        elif not re.match(r'^[A-Za-z0-9_]+$', username):
            errors['username'] = "Логин может содержать только буквы, цифры и подчёркивания"
        elif username == password:
            errors['username'] = "Логин не должен совпадать с паролем"

        #  Проверка пароля
        if not (password and len(password) >= 10):
            errors['password'] = "Пароль должен содержать не менее 10 символов"
        if password != confirm_password:
            errors['confirm_password'] = "Пароли не совпадают"

        if errors:
            return render_template('register.html', error="Ошибка валидации формы", errors=errors)

        hashed_password = generate_password_hash(password)
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                #  Проверка уникальности логина
                cursor.execute("SELECT users_id FROM users WHERE login = %s", (username,))
                if cursor.fetchone():
                    errors['username'] = "Такой логин уже существует"
                    return render_template('register.html', error="Ошибка валидации формы", errors=errors)

                # Вставка пользователя
                cursor.execute(
                    """
                    INSERT INTO users (login, password) VALUES (%s, %s) RETURNING users_id
                    """,
                    (username, hashed_password)
                )
                user_id = cursor.fetchone()[0]
                conn.commit()

                session['logged_in'] = True
                session['username'] = username
                session['user_id'] = user_id

                return redirect(url_for('welcome'))
            except psycopg2.Error as e:
                conn.rollback()
                if "unique" in str(e).lower():
                    errors['username'] = "Такой логин уже существует"
                return render_template('register.html', error="Ошибка базы данных", errors=errors)
            finally:
                cursor.close()
                conn.close()
        else:
            return render_template('register.html', error="Нет соединения с БД")
    return render_template('register.html', errors={})

# Авторизация пользователя
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT users_id, password FROM users WHERE login = %s", (username,))
                result = cursor.fetchone()
                if result:
                    user_id, stored_password = result
                    if check_password_hash(stored_password, password):
                        session['logged_in'] = True
                        session['username'] = username
                        session['user_id'] = user_id
                        return redirect(url_for('welcome'))
                return render_template('login.html', error="Неверный логин или пароль")
            except psycopg2.Error as e:
                return render_template('login.html', error=f"Ошибка БД: {e}")
            finally:
                cursor.close()
                conn.close()
        return render_template('login.html', error="Ошибка подключения к базе данных")
    return render_template('login.html')

# Выход пользователя (очистка сессии)
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# Приветствие после входа (также является главной страницой)
@app.route('/welcome')
@login_required
def welcome():
    return render_template('welcome.html', username=session['username'])

# Каталог товаров (Windows или Office)
@app.route('/catalog')
@login_required
def catalog():
    product_type = request.args.get('product_type', 'windows')
    conn = get_db_connection()
    if not conn:
        return "Ошибка подключения к базе данных"

    cursor = conn.cursor()
    try:
        table = 'windows_products' if product_type == 'windows' else 'office_products'
        template = 'index.html' if product_type == 'windows' else 'index2.html'
        if table == 'windows_products':
            cursor.execute("SELECT windows_products_id, name, description, price, image_path FROM windows_products")
        else:
            cursor.execute("SELECT office_products_id, name, description, price, image_path FROM office_products")
        products = cursor.fetchall()
        product_list = [
            {
                "id": p[0],
                "name": p[1],
                "description": p[2],
                "price": p[3],
                "image": p[4]
            } for p in products
        ]

        return render_template(template, products=product_list, username=session['username'])
    finally:
        cursor.close()
        conn.close()

# Добавление товара в корзину
@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
@login_required
def add_to_cart(item_id):
    cart = session.get('cart', {})
    cart[str(item_id)] = cart.get(str(item_id), 0) + 1
    session['cart'] = cart
    return redirect(request.referrer or url_for('catalog'))

# Удаление одного экземпляра товара из корзины
@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart = session.get('cart', {})
    item_id_str = str(item_id)
    if item_id_str in cart:
        if cart[item_id_str] > 1:
            cart[item_id_str] -= 1
        else:
            del cart[item_id_str]
        session['cart'] = cart
    return redirect(url_for('basket'))

# Просмотр содержимого корзины
@app.route('/basket')
@login_required
def basket():
    cart = session.get('cart', {})
    if not isinstance(cart, dict):
        cart = {}
        session['cart'] = {}

    cart_items = []
    total_price = 0

    if cart:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    SELECT windows_products_id, name, price FROM windows_products WHERE windows_products_id = ANY(%s)
                    UNION
                    SELECT office_products_id, name, price FROM office_products WHERE office_products_id = ANY(%s)
                    """,
                    ([int(i) for i in cart.keys()], [int(i) for i in cart.keys()])
                )
                items = cursor.fetchall()
                for item in items:
                    item_id = str(item[0])
                    if item_id in cart:
                        quantity = cart[item_id]
                        subtotal = item[2] * quantity
                        total_price += subtotal
                        cart_items.append({
                            "id": item[0],
                            "name": item[1],
                            "price": item[2],
                            "quantity": quantity,
                            "subtotal": subtotal
                        })
            except psycopg2.Error as e:
                print(f"Ошибка получения данных корзины: {e}")
                flash("Ошибка базы данных при загрузке корзины", category="danger")
            finally:
                cursor.close()
                conn.close()

    return render_template('basket.html', cart_items=cart_items, total_price=total_price)


# Оформление заказа
@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash("Корзина пуста", category="danger")
        return redirect(url_for('basket'))

    conn = get_db_connection()
    if not conn:
        flash("Ошибка подключения к базе данных", category="danger")
        return redirect(url_for('basket'))

    cursor = conn.cursor()
    try:
        # Проверка карты
        cursor.execute("SELECT card_number FROM users WHERE users_id = %s", (session['user_id'],))
        result = cursor.fetchone()
        card_number = result[0] if result else None

        if not card_number:
            flash("Чтобы оформить заказ, необходимо указать номер карты в профиле.", category="danger")
            return redirect(url_for('basket'))

        # Генерация ID заказа
        cursor.execute("SELECT orders_id FROM orders ORDER BY created_at DESC LIMIT 1")
        last_order = cursor.fetchone()
        if last_order:
            last_num = int(last_order[0][3:])  # убираем 'ORD'
            new_order_num = last_num + 1
        else:
            new_order_num = 1
        order_id = f"ORD{new_order_num:03d}" if new_order_num < 1000 else f"ORD{new_order_num:04d}"

        # Вставка заказа
        cursor.execute(
            "INSERT INTO orders (orders_id, users_id, created_at) VALUES (%s, %s, %s)",
            (order_id, session['user_id'], datetime.now())
        )

        # Вставка товаров заказа
        for item_id, qty in cart.items():
            # Получаем цену
            cursor.execute(
                """
                SELECT price FROM windows_products WHERE windows_products_id = %s
                UNION
                SELECT price FROM office_products WHERE office_products_id = %s
                """,
                (item_id, item_id)
            )
            price_result = cursor.fetchone()
            if not price_result:
                continue

            # Генерация ID позиции
            cursor.execute("SELECT order_items_id FROM order_items ORDER BY order_items_id DESC LIMIT 1")
            last_item = cursor.fetchone()
            if last_item:
                last_item_num = int(last_item[0][5:])
                new_item_num = last_item_num + 1
            else:
                new_item_num = 1
            order_item_id = f"ORDIT{new_item_num:03d}" if new_item_num < 1000 else f"ORDIT{new_item_num:04d}"

            # Вставка позиции
            cursor.execute(
                """
                INSERT INTO order_items (order_items_id, orders_id, product_id, quantity, price)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order_item_id, order_id, item_id, qty, price_result[0])
            )

        conn.commit()
        session['cart'] = {}
        flash("Оплата прошла успешно. Спасибо за заказ!", category="success")

    except Exception as e:
        conn.rollback()
        flash("Ошибка при оформлении заказа", category="danger")
        print(f"Ошибка оформления: {e}")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('basket'))


# Просмотр истории заказов пользователя
@app.route('/order_history')
@login_required
def order_history():
    conn = get_db_connection()
    orders = []

    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT orders_id, created_at FROM orders WHERE users_id = %s ORDER BY created_at DESC",
                (session['user_id'],)
            )
            user_orders = cursor.fetchall()

            for order_id, created_at in user_orders:
                cursor.execute(
                    "SELECT product_id, quantity, price FROM order_items WHERE orders_id = %s",
                    (order_id,)
                )
                order_items = cursor.fetchall()

                items = []
                for product_id, quantity, price in order_items:
                    cursor.execute(
                        """
                        SELECT name FROM windows_products WHERE windows_products_id = %s
                        UNION
                        SELECT name FROM office_products WHERE office_products_id = %s
                        """,
                        (product_id, product_id)
                    )
                    name_result = cursor.fetchone()
                    name = name_result[0] if name_result else "Неизвестный товар"

                    items.append({
                        "name": name,
                        "quantity": quantity,
                        "price": price
                    })

                orders.append({
                    "id": order_id,
                    "created_at": created_at,
                    "items_list": items
                })

        except psycopg2.Error as e:
            flash("Ошибка при загрузке истории заказов", category="danger")
            print(f"Ошибка SQL: {e}")
        finally:
            cursor.close()
            conn.close()

    return render_template("order_history.html", orders=orders)

# Генерация нового ID для заказа (в формате ORD001)
def generate_order_id():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT users_id FROM orders ORDER BY created_at DESC LIMIT 1")
    last_id = cursor.fetchone()

    if last_id:
        last_num = int(last_id[0][3:])  # убираем 'ORD' и берём номер
        new_num = last_num + 1
    else:
        new_num = 1

    cursor.close()
    conn.close()

    return f"ORD{new_num:03d}" if new_num < 1000 else f"ORD{new_num:04d}"

# Генерация нового ID для товара в заказе (в формате ORDIT001)
def generate_order_item_id():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT users_id FROM order_items ORDER BY id DESC LIMIT 1")
    last_id = cursor.fetchone()

    if last_id:
        last_num = int(last_id[0][5:])  # убираем 'ORDIT' и берём номер
        new_num = last_num + 1
    else:
        new_num = 1

    cursor.close()
    conn.close()

    return f"ORDIT{new_num:03d}" if new_num < 1000 else f"ORDIT{new_num:04d}"


def normalize_phone(phone: str) -> str:
    """Преобразует телефон в формат 79259902345 без +, пробелов и 8"""
    if not phone:
        return ''
    phone = re.sub(r'\D', '', phone)  # Удалить все символы, кроме цифр
    if phone.startswith('8') and len(phone) == 11:
        phone = '7' + phone[1:]  # заменить 8 на 7
    elif phone.startswith('9') and len(phone) == 10:
        phone = '7' + phone
    elif phone.startswith('7') and len(phone) == 11:
        pass
    return phone

# Страница редактирования профиля пользователя (туда вносит данные)
@app.route('/user-profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    conn = get_db_connection()
    user_data = {
        'first_name': '',
        'phone': '',
        'email': '',
        'secondary_email': '',
        'card_number': ''
    }

    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name, phone, email, backup_email, card_number FROM users WHERE login = %s",
            (session['username'],)
        )
        data = cursor.fetchone()
        if data:
            user_data = {
                'first_name': data[0] or '',
                'phone': data[1] or '',
                'email': data[2] or '',
                'secondary_email': data[3] or '',
                'card_number': data[4] or ''
            }
        cursor.close()
        conn.close()

    if request.method == 'POST':
        form = request.form
        errors = {}

        first_name = form.get('first_name', '').strip()
        phone = form.get('phone', '').strip()
        email = form.get('email', '').strip()
        secondary_email = form.get('secondary_email', '').strip()
        card_number = form.get('card_number', '').strip()

        # Имя обязательно
        if not first_name:
            errors['first_name'] = "Имя обязательно"

        # Хотя бы телефон или email
        if not email and not phone:
            errors['email'] = "Укажите хотя бы номер телефона или почту"
            errors['phone'] = "Укажите хотя бы номер телефона или почту"

        # Проверка домена email
        if email and not any(email.endswith(d) for d in ['gmail.com', 'outlook.com', 'yandex.ru', 'email.com']):
            errors['email'] = "Недопустимый домен почты"

        # Основная и запасная почта не должны совпадать
        if email and secondary_email and email == secondary_email:
            errors['secondary_email'] = "Основная и запасная почта не могут совпадать"

        # Карта: 16 цифр
        if card_number and not re.match(r'^\d{16}$', card_number):
            errors['card_number'] = "Карта должна содержать 16 цифр"

        # Подключение и сравнение с текущими данными
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email, backup_email, phone, card_number FROM users WHERE login = %s", (session['username'],))
        current_data = cursor.fetchone()
        current_email, current_backup, current_phone, current_card = current_data

        # Проверка: email изменился
        if email and email != (current_email or ''):
            cursor.execute("SELECT login FROM users WHERE email = %s AND login != %s", (email, session['username']))
            if cursor.fetchone():
                errors['email'] = "Эта почта уже используется"

            cursor.execute("SELECT login FROM users WHERE backup_email = %s AND login != %s", (email, session['username']))
            if cursor.fetchone():
                errors['email'] = "Эта почта уже указана как запасная у другого пользователя"

        # Проверка: запасная почта изменилась
        if secondary_email and secondary_email != (current_backup or ''):
            cursor.execute("SELECT login FROM users WHERE backup_email = %s AND login != %s", (secondary_email, session['username']))
            if cursor.fetchone():
                errors['secondary_email'] = "Эта почта уже указана как запасная у другого пользователя"

            cursor.execute("SELECT login FROM users WHERE email = %s AND login != %s", (secondary_email, session['username']))
            if cursor.fetchone():
                errors['secondary_email'] = "Эта почта уже указана как основная у другого пользователя"

        # Проверка телефона (если введён и отличается)
        normalized_phone = normalize_phone(phone)
        if phone and normalized_phone != normalize_phone(current_phone or ''):
            cursor.execute("SELECT login, phone FROM users WHERE login != %s AND phone IS NOT NULL", (session['username'],))
            for login, db_phone in cursor.fetchall():
                if normalize_phone(db_phone) == normalized_phone:
                    errors['phone'] = "Этот номер телефона уже используется"
                    break

        # Проверка карты (если изменилась)
        if card_number and card_number != (current_card or ''):
            cursor.execute("SELECT login FROM users WHERE card_number = %s AND login != %s", (card_number, session['username']))
            if cursor.fetchone():
                errors['card_number'] = "Эта карта уже используется"

        # Если ошибки — вернуть форму с подсветкой
        if errors:
            cursor.close()
            conn.close()
            return render_template('user.html', errors=errors, next_route='welcome', **form)

        # Обновляем данные
        cursor.execute("""
            UPDATE users SET name=%s, phone=%s, email=%s, backup_email=%s, card_number=%s WHERE login=%s
        """, (
            first_name,
            normalized_phone if phone else None,
            email if email else None,
            secondary_email if secondary_email else None,
            card_number if card_number else None,
            session['username']
        ))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Профиль обновлён", category="success")
        return redirect(url_for('welcome'))

    return render_template('user.html', next_route='welcome', **user_data)



if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)

