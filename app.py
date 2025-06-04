from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///orders.db'
app.config['SECRET_KEY'] = 'change-me'
db = SQLAlchemy(app)

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
    quantity = db.Column(db.Integer, default=0)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='created')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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

# Index page shows order form if user is logged in
@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    products = Product.query.all()
    if request.method == 'POST':
        order = Order(user_id=current_user().id)
        db.session.add(order)
        db.session.flush()  # to generate order.id
        for pid, qty in request.form.items():
            if not pid.startswith('product_'):
                continue
            pid_int = int(pid.split('_')[1])
            qty_int = int(qty)
            if qty_int > 0:
                item = OrderItem(order_id=order.id, product_id=pid_int, quantity=qty_int)
                db.session.add(item)
        db.session.commit()
        return redirect(url_for('my_orders'))
    return render_template('order_form.html', products=products)

@app.route('/orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user().id).all()
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
        quantity = int(request.form['quantity'])
        product = Product.query.filter_by(name=name).first()
        if not product:
            product = Product(name=name, quantity=quantity)
            db.session.add(product)
        else:
            product.quantity = quantity
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
    orders = Order.query.order_by(Order.created_at.desc()).all()
    statuses = ['created', 'in_work', 'gathered', 'sent', 'shipped']
    return render_template('admin_orders.html', orders=orders, statuses=statuses)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
