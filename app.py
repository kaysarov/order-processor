from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SECRET_KEY'] = 'change-me'
db = SQLAlchemy(app)

STATUS_NAMES = {
    'created': 'Создан',
    'in_work': 'В работе',
    'gathered': 'Собран',
    'sent': 'Отправлен',
    'shipped': 'Доставлен'
}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    address = db.Column(db.String(200))
    organization = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    delivery_time = db.Column(db.String(50))

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    image_filename = db.Column(db.String(200))
    quantity = db.Column(db.Integer, default=0)
    is_published = db.Column(db.Boolean, default=False)
    is_limited = db.Column(db.Boolean, default=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='created')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_date = db.Column(db.Date)
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

# Authentication helpers

def current_user():
    uid = session.get('user_id')
    if uid:
        return User.query.get(uid)
    return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return dict(current_user=current_user(), STATUS_NAMES=STATUS_NAMES)

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
            session['user_id'] = user.id
            return redirect(url_for('index'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
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
    return render_template('cart.html', items=cart_data)


@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = get_cart()
    items = []
    for pid, qty in cart.items():
        product = Product.query.get(int(pid))
        if product:
            items.append({'product': product, 'qty': qty})
    if request.method == 'POST':
        date_str = request.form['delivery_date']
        delivery_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        comment = request.form.get('comment')
        order = Order(user_id=current_user().id,
                      delivery_date=delivery_date,
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
    return render_template('checkout.html', items=items)

@app.route('/orders')
@login_required
def my_orders():
    query = Order.query.filter_by(user_id=current_user().id)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    if date_from:
        df = datetime.strptime(date_from, '%Y-%m-%d')
        query = query.filter(Order.created_at >= df)
    if date_to:
        dt = datetime.strptime(date_to, '%Y-%m-%d')
        query = query.filter(Order.created_at <= dt)
    orders = query.order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)

# Admin routes
@app.route('/admin')
@login_required
def admin_index():
    if not current_user().is_admin:
        return 'Not authorized'
    return redirect(url_for('admin_products'))

@app.route('/admin/products', methods=['GET', 'POST'])
@login_required
def admin_products():
    if not current_user().is_admin:
        return 'Not authorized'
    if request.method == 'POST':
        name = request.form['name']
        quantity = int(request.form.get('quantity', 0))
        description = request.form.get('description')
        image_file = request.files.get('image')
        is_published = True if request.form.get('is_published') == 'on' else False
        is_limited = True if request.form.get('is_limited') == 'on' else False
        product = Product.query.filter_by(name=name).first()
        if not product:
            product = Product(name=name)
            db.session.add(product)
        product.quantity = quantity
        product.description = description
        if image_file and image_file.filename:
            upload_dir = os.path.join(app.root_path, 'static', 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            fname = secure_filename(image_file.filename)
            image_path = os.path.join('uploads', fname)
            image_file.save(os.path.join(upload_dir, fname))
            product.image_filename = image_path
        product.is_published = is_published
        product.is_limited = is_limited
        db.session.commit()
    products = Product.query.all()
    return render_template('admin_products.html', products=products)

@app.route('/admin/orders', methods=['GET', 'POST'])
@login_required
def admin_orders():
    if not current_user().is_admin:
        return 'Not authorized'
    if request.method == 'POST':
        order_id = int(request.form['order_id'])
        status = request.form['status']
        order = Order.query.get(order_id)
        if order:
            order.status = status
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
    statuses = list(STATUS_NAMES.keys())
    return render_template('admin_orders.html', orders=orders, statuses=statuses,
                           total_qty=total_qty)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
