# Order Processor

Simple Flask web application for managing product inventory and processing orders. The UI uses Bootstrap and supports Russian localization.

## Features
- Admin panel to manage product stock.
- User registration and login.
- Users can browse a storefront, add products to a cart and checkout specifying desired delivery date and time.
- Users may upload a payment receipt so admins can confirm the order.
- Admin can set a delivery interval for each order and update order statuses (created, in_work, gathered, sent, shipped).

## Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   python app.py
   ```

The application will create `orders.db` SQLite database on first run.

## Usage
- Register a new user at `/register`.
- Login via `/login`.
- Admin users must be flagged in the database (`is_admin` set to `True`).
- Admin inventory management is accessible at `/admin/products`.
- Admin order management is accessible at `/admin/orders`.

This project is a minimal demonstration and is not intended for production use.
