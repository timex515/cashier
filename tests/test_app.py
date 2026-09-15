import os
import tempfile
import unittest


class CashierTestCase(unittest.TestCase):
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_file.close()
        os.environ["CASHIER_DB"] = self.db_file.name
        import app

        app.app.config.update(TESTING=True, DATABASE=self.db_file.name)
        with app.app.app_context():
            app.init_db()
            app.seed_users()
        self.app = app.app.test_client()
        self.app.post("/login", data={"name": "زيد", "code": "1"})

    def tearDown(self):
        os.unlink(self.db_file.name)

    def test_product_crud_and_sale(self):
        response = self.app.post(
            "/products/add",
            data={"name": "صنف اختبار", "category": "اختبار", "price": "10", "stock": "5", "sku": "T-1"},
            follow_redirects=True,
        )
        self.assertIn("تمت إضافة الصنف بنجاح".encode(), response.data)
        with self.app.application.app_context():
            import app

            product = app.get_db().execute("SELECT * FROM products WHERE sku='T-1'").fetchone()
            product_id = product["id"]
        self.app.post(
            f"/products/{product_id}/edit",
            data={"name": "صنف معدل", "category": "اختبار", "price": "12", "stock": "5", "sku": "T-1"},
        )
        self.app.post(
            "/sales/checkout",
            data={"product_id": str(product_id), "quantity": "2", "payment_method": "بطاقة"},
        )
        with self.app.application.app_context():
            product = app.get_db().execute("SELECT stock, name FROM products WHERE id=?", (product_id,)).fetchone()
            sale = app.get_db().execute("SELECT id, total FROM sales ORDER BY id DESC LIMIT 1").fetchone()
            sale_date = app.get_db().execute("SELECT date(created_at) FROM sales ORDER BY id DESC LIMIT 1").fetchone()[0]
            self.assertEqual(product["stock"], 3)
            self.assertEqual(product["name"], "صنف معدل")
            self.assertEqual(sale["total"], 24)
        self.assertIn("#1".encode(), self.app.get("/sales?invoice=1").data)
        self.assertIn("صنف معدل".encode(), self.app.get("/sales?product=معدل").data)
        self.assertIn("#1".encode(), self.app.get(f"/sales?date={sale_date}").data)
        invoice_response = self.app.get(f"/sales/{sale['id']}")
        self.assertIn("طباعة الفاتورة".encode(), invoice_response.data)
        blocked_delete = self.app.post(f"/products/{product_id}/delete", follow_redirects=True)
        self.assertIn("لا يمكن حذف صنف مرتبط".encode(), blocked_delete.data)
        self.app.post(
            "/products/add",
            data={"name": "صنف للحذف", "category": "اختبار", "price": "5", "stock": "1", "sku": "T-2"},
        )
        with self.app.application.app_context():
            delete_id = app.get_db().execute("SELECT id FROM products WHERE sku='T-2'").fetchone()["id"]
        self.app.post(f"/products/{delete_id}/delete")
        with self.app.application.app_context():
            self.assertIsNone(app.get_db().execute("SELECT id FROM products WHERE id=?", (delete_id,)).fetchone())

    def test_user_permissions_are_dynamic(self):
        self.app.post("/users/add", data={"name": "أحمد", "code": "22", "screen_id": "1"})
        with self.app.application.app_context():
            import app

            user_id = app.get_db().execute("SELECT id FROM users WHERE name='أحمد'").fetchone()["id"]
            products_screen = app.get_db().execute("SELECT id FROM screens WHERE key='products'").fetchone()["id"]
        self.app.post("/logout")
        login = self.app.post("/login", data={"name": "أحمد", "code": "22"})
        self.assertEqual(login.status_code, 302)
        self.assertTrue(login.headers["Location"].endswith("/"))
        self.assertEqual(self.app.get("/products").status_code, 302)
        self.app.post("/logout")
        self.app.post("/login", data={"name": "زيد", "code": "1"})
        self.app.post(f"/users/{user_id}/permissions", data={"screen_id": [1, products_screen]})
        self.app.post("/logout")
        self.app.post("/login", data={"name": "أحمد", "code": "22"})
        self.assertEqual(self.app.get("/products").status_code, 200)

    def test_credit_sale_records_customer_and_debt(self):
        self.app.post(
            "/products/add",
            data={"name": "صنف آجل", "category": "اختبار", "price": "7500", "stock": "4", "sku": "C-1"},
        )
        with self.app.application.app_context():
            import app

            product_id = app.get_db().execute("SELECT id FROM products WHERE sku='C-1'").fetchone()["id"]
        response = self.app.post(
            "/sales/checkout",
            data={"product_id": str(product_id), "quantity": "2", "payment_method": "آجل", "customer_name": "علي"},
            follow_redirects=True,
        )
        self.assertIn("تم تسجيل البيع".encode(), response.data)
        with self.app.application.app_context():
            sale = app.get_db().execute("SELECT id, payment_method, customer_name, debt_amount, total FROM sales ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(sale["payment_method"], "آجل")
            self.assertEqual(sale["customer_name"], "علي")
            self.assertEqual(sale["debt_amount"], 15000)
            self.assertEqual(self.app.get(f"/sales/{sale['id']}").status_code, 200)
        self.app.post(
            "/sales/checkout",
            data={"product_id": str(product_id), "quantity": "1", "payment_method": "نقدي", "customer_name": "سارة"},
        )
        customers_page = self.app.get("/customers")
        self.assertIn("علي".encode(), customers_page.data)
        self.assertIn("سارة".encode(), customers_page.data)
        statement_page = self.app.get("/customers/علي")
        self.assertIn("كشف الحركات".encode(), statement_page.data)
        self.assertIn("15,000.00 د.ع".encode(), statement_page.data)


if __name__ == "__main__":
    unittest.main()