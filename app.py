from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import re

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SECRET_KEY'] = 'change-me'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

STATUS_TITLES = {
    'created': 'Создан',
    'in_work': 'В работе',
    'gathered': 'Собран',
    'sent': 'Отправлен',
    'shipped': 'Доставлен'
}

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(200))
    organization = db.Column(db.String(200))
    phone = db.Column(db.String(50), unique=True)
    is_blocked = db.Column(db.Boolean, default=False)
    delivery_time = db.Column(db.String(50))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200))
    image_filename = db.Column(db.String(200))  # uploaded image path
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, default=0.0)
    is_published = db.Column(db.Boolean, default=False)
    is_limited = db.Column(db.Boolean, default=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='created')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    desired_delivery = db.Column(db.DateTime)
    delivery_interval = db.Column(db.String(100))
    receipt_filename = db.Column(db.String(200))
    comment = db.Column(db.Text)
    user = db.relationship('User')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer)
    order = db.relationship('Order', backref='items')
    product = db.relationship('Product')

def create_tables():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor
def inject_user():
    return dict(current_user=current_user, status_titles=STATUS_TITLES)

# Routes for registration and login
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        address = request.form['address']
        organization = request.form['organization']
        phone = request.form['phone']
        delivery_time = request.form['delivery_time']
        if User.query.filter_by(username=username).first():
            return 'User exists'
        if not re.fullmatch(r'^(\+7|8)\d{10}$', phone):
            return 'Phone must be Russian format +7XXXXXXXXXX'
        if User.query.filter_by(phone=phone).first():
            return 'Phone already registered'
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            address=address,
            organization=organization,
            phone=phone,
            delivery_time=delivery_time
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if user.is_blocked:
                return 'Account is blocked'
            login_user(user)
            return redirect(url_for('index'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# Shop and cart handling
def get_cart():
    return session.setdefault('cart', {})


@app.route('/')
@login_required
def index():
    products = Product.query.filter_by(is_published=True).all()
    return render_template('shop.html', products=products)


@app.route('/add_to_cart/<int:pid>')
@login_required
def add_to_cart(pid):
    product = Product.query.get(pid)
    if not product or not product.is_published:
        return redirect(url_for('index'))
    cart = get_cart()
    qty = cart.get(str(pid), 0)
    if not product.is_limited or qty < product.quantity:
        cart[str(pid)] = qty + 1
        session['cart'] = cart
    return redirect(url_for('index'))


@app.route('/remove_from_cart/<int:pid>')
@login_required
def remove_from_cart(pid):
    cart = get_cart()
    if str(pid) in cart:
        cart.pop(str(pid))
        session['cart'] = cart
    return redirect(url_for('cart_view'))


@app.route('/cart')
@login_required
def cart_view():
    cart_data = []
    cart = get_cart()
    for pid, qty in cart.items():
        product = Product.query.get(int(pid))
        if product:
            cart_data.append({'product': product, 'qty': qty})
    total = sum(item['product'].price * item['qty'] for item in cart_data)
    return render_template('cart.html', items=cart_data, total=total)


@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = get_cart()
    items = []
    for pid, qty in cart.items():
        product = Product.query.get(int(pid))
        if product:
            items.append({'product': product, 'qty': qty})
    total = sum(i['product'].price * i['qty'] for i in items)
    if request.method == 'POST':
        dt_str = request.form['desired_datetime']
        desired_dt = datetime.strptime(dt_str, '%Y-%m-%dT%H:%M')
        receipt = request.files.get('receipt')
        filename = None
        if receipt and receipt.filename:
            os.makedirs('uploads', exist_ok=True)
            filename = secure_filename(receipt.filename)
            receipt.save(os.path.join('uploads', filename))
        comment = request.form.get('comment')
        order = Order(user_id=current_user.id,
                      desired_delivery=desired_dt,
                      receipt_filename=filename,
                      comment=comment)
        db.session.add(order)
        db.session.flush()
        for item in items:
            db.session.add(OrderItem(order_id=order.id,
                                     product_id=item['product'].id,
                                     quantity=item['qty']))
            if item['product'].is_limited:
                item['product'].quantity -= item['qty']
        db.session.commit()
        session['cart'] = {}
        return redirect(url_for('my_orders'))
    return render_template('checkout.html', items=items, total=total)

@app.route('/orders')
@login_required
def my_orders():
    query = Order.query.filter_by(user_id=current_user.id)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    if date_from:
        df = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Order.created_at >= df)
    if date_to:
        dt = datetime.strptime(date_to, '%Y-%m-%d')
        query = query.filter(Order.created_at <= dt)
    orders = query.order_by(Order.created_at.desc()).all()
    totals = {o.id: sum(it.quantity * it.product.price for it in o.items) for o in orders}
    return render_template('orders.html', orders=orders, order_totals=totals)


@app.route('/upload_receipt/<int:order_id>', methods=['POST'])
@login_required
def upload_receipt(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        return 'Not authorized', 403
    receipt = request.files.get('receipt')
    if receipt and receipt.filename:
        os.makedirs('uploads', exist_ok=True)
        filename = secure_filename(receipt.filename)
        receipt.save(os.path.join('uploads', filename))
        order.receipt_filename = filename
        db.session.commit()
    return redirect(url_for('my_orders'))


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

# Admin routes
@app.route('/admin')
@login_required
def admin_index():
    if not current_user.is_admin:
        return 'Not authorized'
    return redirect(url_for('admin_products'))

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
def admin_products():
    if not current_user.is_admin:
        return 'Not authorized'
    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form.get('quantity', 0))
        price = float(request.form.get('price', 0))
        description = request.form.get('description')
        image = request.files.get('image')
        image_filename = None
        if image and image.filename:
            os.makedirs('uploads/products', exist_ok=True)
            image_filename = secure_filename(image.filename)
            image.save(os.path.join('uploads/products', image_filename))
        is_published = True if request.form.get('is_published') == 'on' else False
        is_limited = True if request.form.get('is_limited') == 'on' else False
        product = Product.query.filter_by(name=name).first()
        if not product:
            product = Product(name=name)
            db.session.add(product)
        product.quantity = quantity
        product.price = price
        product.description = description
        if image_filename:
            product.image_filename = image_filename
        product.is_published = is_published
        product.is_limited = is_limited
        db.session.commit()
    products = Product.query.all()
    return render_template('admin_products.html', products=products)


@app.route('/admin/products/<int:pid>', methods=['GET', 'POST'])
@login_required
def admin_product_edit(pid):
    if not current_user.is_admin:
        return 'Not authorized'
    product = Product.query.get_or_404(pid)
    if request.method == 'POST':
        product.name = request.form['name']
        product.quantity = int(request.form.get('quantity', 0))
        product.price = float(request.form.get('price', 0))
        product.description = request.form.get('description')
        image = request.files.get('image')
        if image and image.filename:
            os.makedirs('uploads/products', exist_ok=True)
            filename = secure_filename(image.filename)
            image.save(os.path.join('uploads/products', filename))
            product.image_filename = filename
        product.is_published = True if request.form.get('is_published') == 'on' else False
        product.is_limited = True if request.form.get('is_limited') == 'on' else False
        db.session.commit()
        return redirect(url_for('admin_products'))
    return render_template('admin_product_edit.html', product=product)

@app.route('/admin/orders', methods=['GET', 'POST'])
@login_required
def admin_orders():
    if not current_user.is_admin:
        return 'Not authorized'
    if request.method == 'POST':
        order_id = int(request.form['order_id'])
        status = request.form['status']
        interval = request.form.get('delivery_interval')
        order = Order.query.get(order_id)
        if order:
            order.status = status
            if interval:
                order.delivery_interval = interval
            db.session.commit()
    query = Order.query
    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter_by(status=status_filter)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    if date_from:
        df = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Order.created_at >= df)
    if date_to:
        dt = datetime.strptime(date_to, '%Y-%m-%d')
        query = query.filter(Order.created_at <= dt)
    orders = query.order_by(Order.created_at.desc()).all()
    total_qty = sum(item.quantity for o in orders for item in o.items)
    total_price = sum(item.quantity * item.product.price for o in orders for item in o.items)
    statuses = list(STATUS_TITLES.keys())
    return render_template('admin_orders.html', orders=orders, statuses=statuses,
                           total_qty=total_qty, total_price=total_price)


@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def admin_users():
    if not current_user.is_admin:
        return 'Not authorized'
    if request.method == 'POST':
        uid = int(request.form['user_id'])
        block = request.form.get('block') == '1'
        user = User.query.get(uid)
        if user:
            user.is_blocked = block
            db.session.commit()
    users = User.query.order_by(User.username).all()
    return render_template('admin_users.html', users=users)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
