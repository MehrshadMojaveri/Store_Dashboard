import json

from django.test import TestCase
from django.urls import reverse

from .models import InventoryMovement, Product, Sale, StoreSettings


class StoreApiTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            name='هدفون آزمایشی',
            category=Product.Category.AUDIO,
            price=250000,
            stock=8,
            icon='headphones',
        )

    def post_json(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_homepage_is_served_by_django(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'نوا | داشبورد مدیریت فروشگاه')
        self.assertContains(response, 'csrf-token')

    def test_products_can_be_created_filtered_and_deleted(self):
        response = self.post_json(
            reverse('products'),
            {
                'name': 'چراغ مطالعه',
                'category': Product.Category.HOME,
                'price': 120000,
                'stock': 3,
            },
        )

        self.assertEqual(response.status_code, 201)
        created = response.json()['product']
        self.assertEqual(created['category_name'], 'خانه')
        self.assertEqual(
            InventoryMovement.objects.filter(
                product_id=created['id'],
                movement_type=InventoryMovement.MovementType.IN,
            ).get().quantity,
            3,
        )

        filtered = self.client.get(reverse('products'), {'search': 'چراغ', 'category': 'home'})
        self.assertEqual([item['id'] for item in filtered.json()['results']], [created['id']])
        deleted = self.client.delete(reverse('product-detail', args=[created['id']]))
        self.assertEqual(deleted.status_code, 409)
        self.assertTrue(Product.objects.filter(pk=created['id']).exists())

        empty_product = Product.objects.create(
            name='محصول بدون سابقه',
            category=Product.Category.HOME,
            price=1000,
            stock=0,
        )
        deleted = self.client.delete(reverse('product-detail', args=[empty_product.pk]))
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Product.objects.filter(pk=empty_product.pk).exists())

    def test_invalid_product_data_is_rejected(self):
        response = self.post_json(
            reverse('products'),
            {'name': '', 'category': 'invalid', 'price': 0, 'stock': -2},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('details', response.json())
        self.assertEqual(Product.objects.count(), 1)

    def test_fractional_stock_and_sale_quantities_are_rejected(self):
        invalid_product = self.post_json(
            reverse('products'),
            {'name': 'محصول نامعتبر', 'price': 1000, 'stock': 1.5},
        )
        self.assertEqual(invalid_product.status_code, 400)

        invalid_sale = self.post_json(
            reverse('sales'),
            {
                'product_id': self.product.pk,
                'quantity': 1.5,
                'customer': 'مریم احمدی',
            },
        )
        self.assertEqual(invalid_sale.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)

    def test_stock_reduction_is_atomic_and_records_movement(self):
        insufficient = self.post_json(
            reverse('reduce-stock'),
            {'product_id': self.product.pk, 'amount': 9},
        )
        self.assertEqual(insufficient.status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertFalse(InventoryMovement.objects.exists())

        response = self.post_json(
            reverse('reduce-stock'),
            {
                'product_id': self.product.pk,
                'amount': 3,
                'reason': 'آسیب‌دیدگی',
                'note': 'بسته‌بندی آسیب دیده',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        movement = InventoryMovement.objects.get()
        self.assertEqual(movement.quantity, 3)
        self.assertEqual(movement.note, 'بسته‌بندی آسیب دیده')

    def test_stock_increase_updates_inventory_and_records_incoming_movement(self):
        response = self.post_json(
            reverse('increase-stock'),
            {
                'product_id': self.product.pk,
                'amount': 12,
                'reason': 'خرید از تامین‌کننده',
                'note': 'فاکتور شماره ۱۲۳',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 20)
        movement = InventoryMovement.objects.get()
        self.assertEqual(movement.movement_type, InventoryMovement.MovementType.IN)
        self.assertEqual(movement.quantity, 12)
        self.assertEqual(movement.reason, 'خرید از تامین‌کننده')
        self.assertEqual(movement.note, 'فاکتور شماره ۱۲۳')

    def test_stock_increase_rejects_invalid_amounts_and_missing_products(self):
        for amount in (0, -1, 1.5):
            response = self.post_json(
                reverse('increase-stock'),
                {'product_id': self.product.pk, 'amount': amount},
            )
            self.assertEqual(response.status_code, 400)
        missing_product = self.post_json(
            reverse('increase-stock'),
            {'product_id': 99999, 'amount': 2},
        )
        self.assertEqual(missing_product.status_code, 404)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertFalse(InventoryMovement.objects.exists())

    def test_sales_consume_stock_and_protect_product_history(self):
        response = self.post_json(
            reverse('sales'),
            {
                'product_id': self.product.pk,
                'quantity': 2,
                'customer': 'مریم احمدی',
                'channel': Sale.Channel.INSTAGRAM,
            },
        )

        self.assertEqual(response.status_code, 201)
        sale = Sale.objects.get()
        self.assertEqual(sale.total, 500000)
        self.assertEqual(sale.channel, Sale.Channel.INSTAGRAM)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertEqual(
            InventoryMovement.objects.get().movement_type,
            InventoryMovement.MovementType.OUT,
        )
        self.assertEqual(
            self.client.delete(reverse('product-detail', args=[self.product.pk])).status_code,
            409,
        )

    def test_cancelled_sale_does_not_reduce_stock(self):
        response = self.post_json(
            reverse('sales'),
            {
                'product_id': self.product.pk,
                'quantity': 2,
                'customer': 'علی رضایی',
                'status': Sale.Status.CANCELLED,
            },
        )

        self.assertEqual(response.status_code, 201)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertFalse(InventoryMovement.objects.exists())

    def test_dashboard_summary_and_settings_are_database_backed(self):
        Sale.objects.create(
            order_number='NV-TEST-0001',
            customer_name='سارا محمدی',
            product=self.product,
            quantity=2,
            unit_price=self.product.price,
        )
        summary = self.client.get(reverse('dashboard-summary')).json()
        self.assertEqual(summary['stats']['total_products'], 1)
        self.assertEqual(summary['stats']['month_revenue'], 500000)
        self.assertEqual(summary['top_products'][0]['units_sold'], 2)

        updated = self.client.patch(
            reverse('store-settings'),
            data=json.dumps({'show_low_stock': False, 'low_stock_threshold': 7}),
            content_type='application/json',
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()['show_low_stock'])
        self.assertEqual(StoreSettings.objects.get().low_stock_threshold, 7)
