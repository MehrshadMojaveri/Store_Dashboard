# نوا | داشبورد مدیریت فروشگاه

## اجرا در ویندوز

از پوشه اصلی پروژه اجرا کنید:

```powershell
.\myvenv\Scripts\python.exe .\StoreDashboard\manage.py migrate
.\myvenv\Scripts\python.exe .\StoreDashboard\manage.py runserver
```

داشبورد در `http://127.0.0.1:8000/` و پنل مدیریت Django در
`http://127.0.0.1:8000/admin/` در دسترس است. برای ساخت کاربر مدیر:

```powershell
.\myvenv\Scripts\python.exe .\StoreDashboard\manage.py createsuperuser
```

برای نصب وابستگی‌ها در یک محیط مجازی تازه:

```powershell
python -m pip install -r requirements.txt
```

پایگاه‌داده پیش‌فرض SQLite است. کلید محرمانه، حالت اشکال‌زدایی و میزبان‌های
مجاز را برای استقرار با متغیرهای محیطی `DJANGO_SECRET_KEY`، `DJANGO_DEBUG`
و `DJANGO_ALLOWED_HOSTS` تنظیم کنید.

قالب داشبورد در `StoreDashboard/templates/index.html` قرار دارد و فایل‌های
استاتیک رابط کاربری در پوشه `assets` نگهداری می‌شوند.

## API

مسیرهای نوشتنی از محافظت CSRF جنگو استفاده می‌کنند و JSON می‌پذیرند.

| مسیر | روش | کاربرد |
| --- | --- | --- |
| `/api/dashboard/` | `GET` | آمار فروش، موجودی، نمودار هفت‌روزه و محصولات پرفروش |
| `/api/products/` | `GET`, `POST` | فهرست/جستجوی محصولات و ثبت محصول |
| `/api/products/<id>/` | `GET`, `PATCH`, `DELETE` | مشاهده، ویرایش یا حذف محصول |
| `/api/stock/` | `POST` | کاهش اتمیک موجودی همراه با ثبت گردش انبار |
| `/api/stock/increase/` | `POST` | افزایش اتمیک موجودی همراه با ثبت ورود انبار |
| `/api/sales/` | `GET`, `POST` | گزارش و ثبت فروش؛ ثبت فروش موجودی را کم می‌کند |
| `/api/settings/` | `GET`, `PATCH` | خواندن و ذخیره تنظیمات فروشگاه |

نمونه ثبت فروش:

```json
{
  "product_id": 1,
  "quantity": 2,
  "customer": "مریم احمدی",
  "channel": "website"
}
```

فروش‌های لغوشده موجودی را تغییر نمی‌دهند و در درآمد گزارش‌ها محاسبه نمی‌شوند.
