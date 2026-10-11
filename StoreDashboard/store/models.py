from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    class Category(models.TextChoices):
        AUDIO = 'audio', 'صوتی و تصویری'
        DIGITAL = 'digital', 'دیجیتال'
        WEARABLE = 'wearable', 'پوشیدنی'
        HOME = 'home', 'خانه'

    name = models.CharField('نام محصول', max_length=160)
    category = models.CharField(
        'دسته‌بندی',
        max_length=20,
        choices=Category.choices,
        default=Category.DIGITAL,
    )
    description = models.TextField('توضیحات', blank=True)
    price = models.PositiveBigIntegerField(
        'قیمت (تومان)',
        validators=[MinValueValidator(1)],
    )
    stock = models.PositiveIntegerField('موجودی', default=0)
    icon = models.CharField('نماد', max_length=40, default='inventory_2')
    created_at = models.DateTimeField('تاریخ ایجاد', auto_now_add=True)
    updated_at = models.DateTimeField('آخرین به‌روزرسانی', auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'محصول'
        verbose_name_plural = 'محصولات'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name='product_price_gt_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name='product_stock_nonnegative',
            ),
        ]

    def __str__(self):
        return self.name


class Sale(models.Model):
    class Channel(models.TextChoices):
        WEBSITE = 'website', 'وب‌سایت'
        INSTAGRAM = 'instagram', 'اینستاگرام'
        MARKETPLACE = 'marketplace', 'دیجی‌کالا'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'تکمیل شده'
        PENDING = 'pending', 'در حال پردازش'
        CANCELLED = 'cancelled', 'لغو شده'

    order_number = models.CharField('شماره سفارش', max_length=32, unique=True)
    customer_name = models.CharField('نام مشتری', max_length=160)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='sales',
        verbose_name='محصول',
    )
    quantity = models.PositiveIntegerField(
        'تعداد',
        validators=[MinValueValidator(1)],
    )
    unit_price = models.PositiveBigIntegerField('قیمت واحد (تومان)')
    channel = models.CharField(
        'کانال فروش',
        max_length=20,
        choices=Channel.choices,
        default=Channel.WEBSITE,
    )
    status = models.CharField(
        'وضعیت',
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'فروش'
        verbose_name_plural = 'فروش‌ها'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='sale_quantity_gt_zero',
            ),
        ]

    @property
    def total(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.order_number


class InventoryMovement(models.Model):
    class MovementType(models.TextChoices):
        IN = 'in', 'ورود'
        OUT = 'out', 'خروج'

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='inventory_movements',
        verbose_name='محصول',
    )
    movement_type = models.CharField(
        'نوع گردش',
        max_length=3,
        choices=MovementType.choices,
    )
    quantity = models.PositiveIntegerField(
        'تعداد',
        validators=[MinValueValidator(1)],
    )
    reason = models.CharField('علت', max_length=100, blank=True)
    note = models.TextField('یادداشت', blank=True)
    created_at = models.DateTimeField('تاریخ ثبت', auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'گردش انبار'
        verbose_name_plural = 'گردش‌های انبار'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='inventory_movement_quantity_gt_zero',
            ),
        ]

    def __str__(self):
        return f'{self.get_movement_type_display()} - {self.product}'


class StoreSettings(models.Model):
    notifications_enabled = models.BooleanField('اعلان‌های فروش', default=True)
    show_low_stock = models.BooleanField('نمایش موجودی کم', default=True)
    low_stock_threshold = models.PositiveIntegerField('حد موجودی کم', default=5)

    class Meta:
        verbose_name = 'تنظیمات فروشگاه'
        verbose_name_plural = 'تنظیمات فروشگاه'

    def __str__(self):
        return 'تنظیمات فروشگاه'
