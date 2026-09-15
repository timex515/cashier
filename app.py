from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
default_database = "/tmp/cashier.sqlite3" if os.environ.get("VERCEL") else BASE_DIR / "cashier.sqlite3"
DATABASE = Path(os.environ.get("CASHIER_DB", default_database))
app = Flask(__name__)
app.config.update(
    DATABASE=str(DATABASE),
    SECRET_KEY=os.environ.get("CASHIER_SECRET", "cashier-development-key"),
)

LOGIN_NAME = "زيد"
LOGIN_CODE = "1"
SCREEN_DEFINITIONS = {
    "dashboard": {"name": "لوحة التحكم", "icon": "⌂", "endpoint": "dashboard", "order": 1},
    "products": {"name": "الأصناف والمخزون", "icon": "▦", "endpoint": "products", "order": 2},
    "sales": {"name": "سجل المبيعات", "icon": "◷", "endpoint": "sales", "order": 3},
    "users": {"name": "إدارة المستخدمين", "icon": "♙", "endpoint": "users", "order": 4},
    "customers": {"name": "العملاء", "icon": "♧", "endpoint": "customers", "order": 5},
}


@app.before_request
def require_login():
    if request.endpoint in {"login", "static"}:
        return None
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    screen_key = next(
        (key for key, screen in SCREEN_DEFINITIONS.items() if screen["endpoint"] == request.endpoint),
        None,
    )
    if screen_key is None and request.endpoint:
        screen_key = next(
            (key for key in SCREEN_DEFINITIONS if request.endpoint.startswith(f"{key}_")),
            None,
        )
    if screen_key and not has_screen_access(screen_key):
        flash("لا تملك صلاحية الوصول إلى هذه الواجهة", "error")
        return redirect_to_allowed_screen()
    return None


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'عام',
            price REAL NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            sku TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total REAL NOT NULL,
            payment_method TEXT NOT NULL DEFAULT 'نقدي',
            customer_name TEXT,
            debt_amount REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            price REAL NOT NULL,
            subtotal REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            code_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS screens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '□',
            endpoint TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 99,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS user_screens (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            screen_id INTEGER NOT NULL REFERENCES screens(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, screen_id)
        );
        """
    )
    columns = {row["name"] for row in db.execute("PRAGMA table_info(sales)").fetchall()}
    if "customer_name" not in columns:
        db.execute("ALTER TABLE sales ADD COLUMN customer_name TEXT")
    if "debt_amount" not in columns:
        db.execute("ALTER TABLE sales ADD COLUMN debt_amount REAL NOT NULL DEFAULT 0")
    for key, screen in SCREEN_DEFINITIONS.items():
        db.execute(
            "INSERT OR IGNORE INTO screens (key, name, icon, endpoint, sort_order) VALUES (?, ?, ?, ?, ?)",
            (key, screen["name"], screen["icon"], screen["endpoint"], screen["order"]),
        )
    db.commit()


def seed_users() -> None:
    db = get_db()
    admin = db.execute("SELECT id FROM users WHERE name=?", (LOGIN_NAME,)).fetchone()
    if admin is None:
        cursor = db.execute(
            "INSERT INTO users (name, code_hash, is_admin) VALUES (?, ?, 1)",
            (LOGIN_NAME, generate_password_hash(LOGIN_CODE)),
        )
        admin_id = cursor.lastrowid
    else:
        admin_id = admin["id"]
    screen_ids = db.execute("SELECT id FROM screens").fetchall()
    db.executemany(
        "INSERT OR IGNORE INTO user_screens (user_id, screen_id) VALUES (?, ?)",
        [(admin_id, screen["id"]) for screen in screen_ids],
    )
    db.commit()


def seed_demo_data() -> None:
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        db.executemany(
            "INSERT INTO products (name, category, price, stock, sku) VALUES (?, ?, ?, ?, ?)",
            [
                ("قهوة عربية", "مشروبات", 12.50, 48, "DRK-001"),
                ("ساندويتش دجاج", "وجبات", 24.00, 22, "FOD-002"),
                ("مياه معدنية", "مشروبات", 2.00, 100, "DRK-003"),
                ("كيك الشوكولاتة", "حلويات", 16.00, 15, "SWT-004"),
            ],
        )
        db.commit()


def money(value: float) -> str:
    return f"{value:,.2f} د.ع"


app.jinja_env.filters["money"] = money


@app.context_processor
def inject_globals() -> dict[str, Any]:
    db = get_db()
    screens = []
    if session.get("logged_in"):
        screens = get_allowed_screens()
    return {
        "current_year": datetime.now().year,
        "login_name": session.get("user_name", LOGIN_NAME),
        "is_admin": bool(session.get("is_admin")),
        "allowed_screens": screens,
    }


def get_allowed_screens() -> list[sqlite3.Row]:
    db = get_db()
    if session.get("is_admin"):
        return db.execute("SELECT * FROM screens WHERE active=1 ORDER BY sort_order, id").fetchall()
    return db.execute(
        "SELECT screens.* FROM screens JOIN user_screens ON user_screens.screen_id=screens.id "
        "WHERE user_screens.user_id=? AND screens.active=1 ORDER BY sort_order, id",
        (session.get("user_id"),),
    ).fetchall()


def has_screen_access(screen_key: str) -> bool:
    if session.get("is_admin"):
        return True
    return any(screen["key"] == screen_key for screen in get_allowed_screens())


def redirect_to_allowed_screen():
    allowed = get_allowed_screens()
    if allowed:
        return redirect(url_for(allowed[0]["endpoint"]))
    session.clear()
    flash("لا توجد واجهات مفعلة لهذا المستخدم", "error")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE name=? AND active=1", (name,)).fetchone()
        if user and check_password_hash(user["code_hash"], code):
            session["logged_in"] = True
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["is_admin"] = bool(user["is_admin"])
            return redirect_to_allowed_screen()
        flash("اسم المستخدم أو الرمز غير صحيح", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/users")
def users():
    db = get_db()
    user_rows = db.execute(
        "SELECT users.*, COUNT(user_screens.screen_id) AS permission_count FROM users "
        "LEFT JOIN user_screens ON user_screens.user_id=users.id GROUP BY users.id ORDER BY users.is_admin DESC, users.id DESC"
    ).fetchall()
    screens = db.execute("SELECT * FROM screens WHERE active=1 ORDER BY sort_order, id").fetchall()
    permissions = {
        user["id"]: {row["screen_id"] for row in db.execute("SELECT screen_id FROM user_screens WHERE user_id=?", (user["id"],)).fetchall()}
        for user in user_rows
    }
    return render_template("users.html", users=user_rows, screens=screens, permissions=permissions)


@app.post("/users/add")
def add_user():
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "")
    screen_ids = request.form.getlist("screen_id")
    if not name or not code:
        flash("أدخل اسم المستخدم والرمز", "error")
        return redirect(url_for("users"))
    db = get_db()
    try:
        cursor = db.execute("INSERT INTO users (name, code_hash) VALUES (?, ?)", (name, generate_password_hash(code)))
        user_id = cursor.lastrowid
        valid_ids = {str(row["id"]) for row in db.execute("SELECT id FROM screens WHERE active=1").fetchall()}
        db.executemany(
            "INSERT INTO user_screens (user_id, screen_id) VALUES (?, ?)",
            [(user_id, int(screen_id)) for screen_id in screen_ids if screen_id in valid_ids],
        )
        db.commit()
        flash("تم إنشاء المستخدم وتطبيق صلاحياته", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("اسم المستخدم مستخدم مسبقًا", "error")
    return redirect(url_for("users"))


@app.post("/users/<int:user_id>/permissions")
def update_permissions(user_id: int):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if user is None:
        flash("المستخدم غير موجود", "error")
        return redirect(url_for("users"))
    if user["is_admin"]:
        flash("زيد لديه كل الصلاحيات دائمًا", "error")
        return redirect(url_for("users"))
    screen_ids = {int(value) for value in request.form.getlist("screen_id")}
    valid_ids = {row["id"] for row in db.execute("SELECT id FROM screens WHERE active=1").fetchall()}
    db.execute("DELETE FROM user_screens WHERE user_id=?", (user_id,))
    db.executemany(
        "INSERT INTO user_screens (user_id, screen_id) VALUES (?, ?)",
        [(user_id, screen_id) for screen_id in screen_ids if screen_id in valid_ids],
    )
    db.commit()
    flash("تم تحديث واجهات المستخدم", "success")
    return redirect(url_for("users"))


@app.route("/")
def dashboard():
    db = get_db()
    stats = {
        "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "stock": db.execute("SELECT COALESCE(SUM(stock), 0) FROM products").fetchone()[0],
        "sales": db.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
        "revenue": db.execute("SELECT COALESCE(SUM(total), 0) FROM sales").fetchone()[0],
    }
    recent_sales = db.execute(
        "SELECT id, total, payment_method, created_at FROM sales ORDER BY id DESC LIMIT 6"
    ).fetchall()
    low_stock = db.execute(
        "SELECT * FROM products WHERE stock <= 5 ORDER BY stock, name LIMIT 5"
    ).fetchall()
    products = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    return render_template("dashboard.html", stats=stats, recent_sales=recent_sales, low_stock=low_stock, products=products)


@app.route("/products")
def products():
    db = get_db()
    query = request.args.get("q", "").strip()
    if query:
        items = db.execute(
            "SELECT * FROM products WHERE name LIKE ? OR category LIKE ? OR sku LIKE ? ORDER BY id DESC",
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        items = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template("products.html", products=items, query=query)


@app.post("/products/add")
def add_product():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "عام").strip() or "عام"
    sku = request.form.get("sku", "").strip() or None
    try:
        price = float(request.form.get("price", "0"))
        stock = int(request.form.get("stock", "0"))
        if not name or price < 0 or stock < 0:
            raise ValueError
        db = get_db()
        db.execute(
            "INSERT INTO products (name, category, price, stock, sku) VALUES (?, ?, ?, ?, ?)",
            (name, category, price, stock, sku),
        )
        db.commit()
        flash("تمت إضافة الصنف بنجاح", "success")
    except (ValueError, sqlite3.IntegrityError):
        flash("تحقق من البيانات، وتأكد أن رمز الصنف غير مكرر", "error")
    return redirect(url_for("products"))


@app.post("/products/<int:product_id>/edit")
def edit_product(product_id: int):
    try:
        price = float(request.form.get("price", "0"))
        stock = int(request.form.get("stock", "0"))
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "عام").strip() or "عام"
        sku = request.form.get("sku", "").strip() or None
        if not name or price < 0 or stock < 0:
            raise ValueError
        db = get_db()
        db.execute(
            "UPDATE products SET name=?, category=?, price=?, stock=?, sku=? WHERE id=?",
            (name, category, price, stock, sku, product_id),
        )
        db.commit()
        flash("تم تحديث بيانات الصنف", "success")
    except (ValueError, sqlite3.IntegrityError):
        flash("تعذر تحديث الصنف. راجع البيانات", "error")
    return redirect(url_for("products"))


@app.post("/products/<int:product_id>/delete")
def delete_product(product_id: int):
    db = get_db()
    try:
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
        db.commit()
        flash("تم حذف الصنف", "success")
    except sqlite3.IntegrityError:
        flash("لا يمكن حذف صنف مرتبط بفاتورة سابقة", "error")
    return redirect(url_for("products"))


@app.route("/sales")
def sales():
    db = get_db()
    invoice_number = request.args.get("invoice", "").strip()
    product_name = request.args.get("product", "").strip()
    sale_date = request.args.get("date", "").strip()
    conditions = []
    parameters: list[object] = []
    if invoice_number:
        try:
            conditions.append("sales.id = ?")
            parameters.append(int(invoice_number.lstrip("#")))
        except ValueError:
            conditions.append("1 = 0")
    if product_name:
        conditions.append("EXISTS (SELECT 1 FROM sale_items filter_items WHERE filter_items.sale_id = sales.id AND filter_items.product_name LIKE ?)")
        parameters.append(f"%{product_name}%")
    if sale_date:
        conditions.append("date(sales.created_at) = date(?)")
        parameters.append(sale_date)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    history = db.execute(
        f"SELECT sales.id, sales.total, sales.payment_method, sales.customer_name, sales.debt_amount, sales.created_at, "
        f"GROUP_CONCAT(DISTINCT sale_items.product_name) AS product_names "
        f"FROM sales LEFT JOIN sale_items ON sale_items.sale_id = sales.id "
        f"{where_clause} GROUP BY sales.id ORDER BY sales.id DESC",
        parameters,
    ).fetchall()
    return render_template(
        "sales.html",
        sales=history,
        filters={"invoice": invoice_number, "product": product_name, "date": sale_date},
    )


@app.route("/sales/<int:sale_id>")
def sale_detail(sale_id: int):
    db = get_db()
    sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if sale is None:
        flash("الفاتورة غير موجودة", "error")
        return redirect(url_for("sales"))
    items = db.execute(
        "SELECT product_name, quantity, price, subtotal FROM sale_items WHERE sale_id=? ORDER BY id",
        (sale_id,),
    ).fetchall()
    return render_template("invoice.html", sale=sale, items=items)


@app.route("/customers")
def customers():
    db = get_db()
    customer_rows = db.execute(
        "SELECT customer_name, COUNT(*) AS invoice_count, SUM(total) AS total_purchases, "
        "SUM(CASE WHEN payment_method='آجل' THEN debt_amount ELSE 0 END) AS debt_total, "
        "SUM(CASE WHEN payment_method!='آجل' THEN total ELSE 0 END) AS paid_total, "
        "MAX(created_at) AS last_purchase FROM sales "
        "WHERE customer_name IS NOT NULL AND TRIM(customer_name) != '' "
        "GROUP BY customer_name COLLATE NOCASE ORDER BY last_purchase DESC"
    ).fetchall()
    stats = {
        "customers": len(customer_rows),
        "purchases": sum(row["total_purchases"] or 0 for row in customer_rows),
        "debt": sum(row["debt_total"] or 0 for row in customer_rows),
    }
    return render_template("customers.html", customers=customer_rows, stats=stats)


@app.route("/customers/<path:customer_name>")
def customer_statement(customer_name: str):
    db = get_db()
    invoices = db.execute(
        "SELECT id, total, payment_method, customer_name, debt_amount, created_at FROM sales "
        "WHERE customer_name = ? COLLATE NOCASE ORDER BY id DESC",
        (customer_name,),
    ).fetchall()
    if not invoices:
        flash("العميل غير موجود أو لا يملك فواتير مسجلة", "error")
        return redirect(url_for("customers"))
    summary = {
        "total": sum(row["total"] or 0 for row in invoices),
        "debt": sum(row["debt_amount"] or 0 for row in invoices),
        "paid": sum(row["total"] or 0 for row in invoices if row["payment_method"] != "آجل"),
    }
    return render_template("customer_statement.html", customer_name=invoices[0]["customer_name"], invoices=invoices, summary=summary)


@app.post("/sales/checkout")
def checkout():
    product_ids = request.form.getlist("product_id")
    quantities = request.form.getlist("quantity")
    payment_method = request.form.get("payment_method", "نقدي")
    customer_name = request.form.get("customer_name", "").strip() or None
    if payment_method == "آجل" and not customer_name:
        flash("أدخل اسم الزبون عند البيع بالدين", "error")
        return redirect(url_for("dashboard"))
    if not product_ids:
        flash("أضف صنفًا واحدًا على الأقل إلى السلة", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    try:
        cart: list[tuple[sqlite3.Row, int, float]] = []
        total = 0.0
        for product_id, raw_quantity in zip(product_ids, quantities):
            quantity = int(raw_quantity)
            product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
            if product is None or quantity <= 0 or quantity > product["stock"]:
                raise ValueError
            subtotal = product["price"] * quantity
            cart.append((product, quantity, subtotal))
            total += subtotal
        debt_amount = total if payment_method == "آجل" else 0
        cursor = db.execute(
            "INSERT INTO sales (total, payment_method, customer_name, debt_amount) VALUES (?, ?, ?, ?)",
            (total, payment_method, customer_name, debt_amount),
        )
        sale_id = cursor.lastrowid
        for product, quantity, subtotal in cart:
            db.execute(
                "INSERT INTO sale_items (sale_id, product_id, product_name, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?, ?)",
                (sale_id, product["id"], product["name"], quantity, product["price"], subtotal),
            )
            db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (quantity, product["id"]))
        db.commit()
        flash(f"تم تسجيل البيع #{sale_id} بإجمالي {money(total)}", "success")
    except (ValueError, sqlite3.Error):
        db.rollback()
        flash("تعذر إتمام البيع. تحقق من الكميات والمخزون", "error")
    return redirect(url_for("dashboard"))


with app.app_context():
    init_db()
    seed_demo_data()
    seed_users()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )