import json
import re
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import BigIntegerField, Count, F, ProtectedError, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import InventoryMovement, Product, Sale, StoreSettings


CATEGORY_ICONS = {
    Product.Category.AUDIO: 'headphones',
    Product.Category.DIGITAL: 'smartphone',
    Product.Category.WEARABLE: 'watch',
    Product.Category.HOME: 'desk_lamp',
}


def dashboard(request):
    return render(request, 'index.html')


def error_response(message, status=400, details=None):
    body = {'error': message}
    if details:
        body['details'] = details
    return JsonResponse(body, status=status)


def read_json(request):
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, error_response('بدنه درخواست باید JSON معتبر باشد.')
    if not isinstance(payload, dict):
        return None, error_response('بدنه درخواست باید یک شیء JSON باشد.')
    return payload, None


def validation_details(error):
    if hasattr(error, 'message_dict'):
        return error.message_dict
    return {'non_field_errors': error.messages}


def parse_integer(value):
    if isinstance(value, bool):
        raise ValueError
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r'[+-]?\d+', value.strip()):
        return int(value)
    raise ValueError


def serialize_product(product):
    return {
        'id': product.pk,
        'name': product.name,
        'category': product.category,
        'category_name': product.get_category_display(),
        'description': product.description,
        'price': product.price,
        'stock': product.stock,
        'icon': product.icon,
        'created_at': product.created_at.isoformat(),
        'updated_at': product.updated_at.isoformat(),
    }


def serialize_sale(sale):
    return {
        'id': sale.pk,
        'order': sale.order_number,
        'customer': sale.customer_name,
        'product_id': sale.product_id,
        'product': sale.product.name,
        'icon': sale.product.icon,
        'quantity': sale.quantity,
        'unit_price': sale.unit_price,
        'total': sale.total,
        'channel': sale.channel,
        'channel_name': sale.get_channel_display(),
        'status': sale.status,
        'status_name': sale.get_status_display(),
        'created_at': sale.created_at.isoformat(),
    }


@require_http_methods(['GET', 'POST'])
def products(request):
    if request.method == 'GET':
        queryset = Product.objects.all()
        search = request.GET.get('search', '').strip()
        category = request.GET.get('category', '').strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category and category != 'all':
            queryset = queryset.filter(category=category)
        return JsonResponse({'results': [serialize_product(item) for item in queryset]})

    data, error = read_json(request)
    if error:
        return error
    allowed_fields = {'name', 'category', 'description', 'price', 'stock'}
    unknown_fields = set(data) - allowed_fields
    if unknown_fields:
        return error_response('فیلدهای درخواست معتبر نیستند.', details={'fields': sorted(unknown_fields)})
    try:
        if 'price' in data:
            data['price'] = parse_integer(data['price'])
        if 'stock' in data:
            data['stock'] = parse_integer(data['stock'])
    except ValueError:
        return error_response('قیمت و موجودی باید عدد صحیح باشند.')
    product = Product(
        name=data.get('name', ''),
        category=data.get('category', Product.Category.DIGITAL),
        description=data.get('description', ''),
        price=data.get('price', 0),
        stock=data.get('stock', 0),
    )
    product.icon = CATEGORY_ICONS.get(product.category, 'inventory_2')
    try:
        product.full_clean()
        with transaction.atomic():
            product.save()
            if product.stock:
                InventoryMovement.objects.create(
                    product=product,
                    movement_type=InventoryMovement.MovementType.IN,
                    quantity=product.stock,
                    reason='موجودی اولیه',
                )
    except ValidationError as exc:
        return error_response('اطلاعات محصول معتبر نیست.', details=validation_details(exc))
    return JsonResponse({'product': serialize_product(product)}, status=201)


@require_http_methods(['GET', 'PATCH', 'DELETE'])
def product_detail(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if request.method == 'GET':
        return JsonResponse({'product': serialize_product(product)})

    if request.method == 'DELETE':
        try:
            product.delete()
        except ProtectedError:
            return error_response(
                'محصولی که سابقه فروش یا گردش انبار دارد قابل حذف نیست.',
                status=409,
            )
        return JsonResponse({'deleted': True})

    data, error = read_json(request)
    if error:
        return error
    allowed_fields = {'name', 'category', 'description', 'price'}
    unknown_fields = set(data) - allowed_fields
    if unknown_fields:
        return error_response('فیلدهای درخواست معتبر نیستند.', details={'fields': sorted(unknown_fields)})
    try:
        if 'price' in data:
            data['price'] = parse_integer(data['price'])
    except ValueError:
        return error_response('قیمت باید عدد صحیح باشد.')
    for field in allowed_fields & data.keys():
        setattr(product, field, data[field])
    if 'category' in data:
        product.icon = CATEGORY_ICONS.get(product.category, 'inventory_2')
    try:
        product.full_clean()
        product.save()
    except ValidationError as exc:
        return error_response('اطلاعات محصول معتبر نیست.', details=validation_details(exc))
    return JsonResponse({'product': serialize_product(product)})


@require_http_methods(['POST'])
def reduce_stock(request):
    data, error = read_json(request)
    if error:
        return error
    try:
        product_id = parse_integer(data.get('product_id'))
        amount = parse_integer(data.get('amount'))
    except (TypeError, ValueError):
        return error_response('شناسه محصول و تعداد کاهش باید عدد صحیح باشند.')
    if amount < 1:
        return error_response('تعداد کاهش باید حداقل ۱ باشد.')

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product_id)
            if product.stock < amount:
                return error_response('موجودی محصول برای این عملیات کافی نیست.', status=409)
            product.stock -= amount
            product.save(update_fields=['stock', 'updated_at'])
            InventoryMovement.objects.create(
                product=product,
                movement_type=InventoryMovement.MovementType.OUT,
                quantity=amount,
                reason=str(data.get('reason', 'کاهش موجودی'))[:100],
                note=str(data.get('note', ''))[:5000],
            )
    except Product.DoesNotExist:
        return error_response('محصول موردنظر پیدا نشد.', status=404)
    return JsonResponse({'product': serialize_product(product)})


@require_http_methods(['POST'])
def increase_stock(request):
    data, error = read_json(request)
    if error:
        return error
    try:
        product_id = parse_integer(data.get('product_id'))
        amount = parse_integer(data.get('amount'))
    except (TypeError, ValueError):
        return error_response('شناسه محصول و تعداد افزایش باید عدد صحیح باشند.')
    if amount < 1:
        return error_response('تعداد افزایش باید حداقل ۱ باشد.')

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product_id)
            if product.stock + amount > 2147483647:
                return error_response('موجودی پس از افزایش از حد مجاز بیشتر می‌شود.')
            product.stock += amount
            product.save(update_fields=['stock', 'updated_at'])
            InventoryMovement.objects.create(
                product=product,
                movement_type=InventoryMovement.MovementType.IN,
                quantity=amount,
                reason=str(data.get('reason', 'افزایش موجودی'))[:100],
                note=str(data.get('note', ''))[:5000],
            )
    except Product.DoesNotExist:
        return error_response('محصول موردنظر پیدا نشد.', status=404)
    return JsonResponse({'product': serialize_product(product)})


@require_http_methods(['GET', 'POST'])
def sales(request):
    if request.method == 'GET':
        queryset = Sale.objects.select_related('product')
        status_filter = request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return JsonResponse({'results': [serialize_sale(item) for item in queryset]})

    data, error = read_json(request)
    if error:
        return error
    try:
        product_id = parse_integer(data.get('product_id'))
        quantity = parse_integer(data.get('quantity', 1))
    except (TypeError, ValueError):
        return error_response('شناسه محصول و تعداد باید عدد صحیح باشند.')
    customer = str(data.get('customer', '')).strip()
    status = data.get('status', Sale.Status.COMPLETED)
    if not customer or len(customer) > 160:
        return error_response('نام مشتری الزامی و حداکثر ۱۶۰ نویسه است.')
    if quantity < 1:
        return error_response('تعداد فروش باید حداقل ۱ باشد.')
    if status not in Sale.Status.values:
        return error_response('وضعیت سفارش معتبر نیست.')
    channel = data.get('channel', Sale.Channel.WEBSITE)
    if channel not in Sale.Channel.values:
        return error_response('کانال فروش معتبر نیست.')

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=product_id)
            if status != Sale.Status.CANCELLED and product.stock < quantity:
                return error_response('موجودی محصول برای ثبت این فروش کافی نیست.', status=409)
            sale = Sale.objects.create(
                order_number=f'NV-{uuid.uuid4().hex[:10].upper()}',
                customer_name=customer,
                product=product,
                quantity=quantity,
                unit_price=product.price,
                status=status,
                channel=channel,
            )
            if status != Sale.Status.CANCELLED:
                product.stock -= quantity
                product.save(update_fields=['stock', 'updated_at'])
                InventoryMovement.objects.create(
                    product=product,
                    movement_type=InventoryMovement.MovementType.OUT,
                    quantity=quantity,
                    reason=f'فروش {sale.order_number}',
                )
    except Product.DoesNotExist:
        return error_response('محصول موردنظر پیدا نشد.', status=404)
    return JsonResponse({'sale': serialize_sale(sale)}, status=201)


@require_http_methods(['GET'])
def dashboard_summary(request):
    today = timezone.localdate()
    month_start = today - timedelta(days=29)
    active_sales = Sale.objects.exclude(status=Sale.Status.CANCELLED)
    today_sales = active_sales.filter(created_at__date=today)
    today_revenue = today_sales.aggregate(
        total=Sum(F('quantity') * F('unit_price'), output_field=BigIntegerField()),
    )['total'] or 0

    daily_rows = (
        active_sales.filter(created_at__date__gte=today - timedelta(days=6))
        .values('created_at__date')
        .annotate(total=Sum(F('quantity') * F('unit_price'), output_field=BigIntegerField()))
        .annotate(orders=Count('pk'))
        .order_by('created_at__date')
    )
    daily_revenue = {
        row['created_at__date']: (row['total'] or 0, row['orders'])
        for row in daily_rows
    }
    sales_by_day = [
        {
            'date': (today - timedelta(days=offset)).isoformat(),
            'revenue': daily_revenue.get(today - timedelta(days=offset), (0, 0))[0],
            'orders': daily_revenue.get(today - timedelta(days=offset), (0, 0))[1],
        }
        for offset in range(6, -1, -1)
    ]

    top_products = (
        Product.objects.annotate(
            units_sold=Sum(
                'sales__quantity',
                filter=Q(
                    sales__status__in=[Sale.Status.COMPLETED, Sale.Status.PENDING],
                    sales__created_at__date__gte=month_start,
                ),
            ),
            revenue=Sum(
                F('sales__quantity') * F('sales__unit_price'),
                filter=Q(
                    sales__status__in=[Sale.Status.COMPLETED, Sale.Status.PENDING],
                    sales__created_at__date__gte=month_start,
                ),
                output_field=BigIntegerField(),
            ),
        )
        .filter(units_sold__gt=0)
        .order_by('-units_sold', 'name')[:10]
    )

    settings, _ = StoreSettings.objects.get_or_create(pk=1)
    total_products = Product.objects.count()
    return JsonResponse(
        {
            'stats': {
                'total_products': total_products,
                'available_products': Product.objects.filter(stock__gt=0).count(),
                'out_of_stock_products': Product.objects.filter(stock=0).count(),
                'today_revenue': today_revenue,
                'today_orders': today_sales.count(),
                'month_revenue': active_sales.filter(created_at__date__gte=month_start).aggregate(
                    total=Sum(F('quantity') * F('unit_price'), output_field=BigIntegerField()),
                )['total'] or 0,
                'month_orders': active_sales.filter(created_at__date__gte=month_start).count(),
                'inventory_value': Product.objects.aggregate(
                    total=Sum(F('price') * F('stock'), output_field=BigIntegerField()),
                )['total'] or 0,
                'inventory_units': Product.objects.aggregate(total=Sum('stock'))['total'] or 0,
                'channels': [
                    {'channel': row['channel'], 'count': row['count']}
                    for row in active_sales.filter(created_at__date__gte=month_start)
                    .values('channel')
                    .annotate(count=Count('pk'))
                ],
            },
            'sales_by_day': sales_by_day,
            'top_products': [
                {
                    **serialize_product(product),
                    'units_sold': product.units_sold or 0,
                    'revenue': product.revenue or 0,
                }
                for product in top_products
            ],
            'settings': {
                'notifications_enabled': settings.notifications_enabled,
                'show_low_stock': settings.show_low_stock,
                'low_stock_threshold': settings.low_stock_threshold,
            },
        }
    )


@require_http_methods(['GET', 'PATCH'])
def store_settings(request):
    settings, _ = StoreSettings.objects.get_or_create(pk=1)
    if request.method == 'GET':
        return JsonResponse(
            {
                'notifications_enabled': settings.notifications_enabled,
                'show_low_stock': settings.show_low_stock,
                'low_stock_threshold': settings.low_stock_threshold,
            }
        )
    data, error = read_json(request)
    if error:
        return error
    allowed_fields = {'notifications_enabled', 'show_low_stock', 'low_stock_threshold'}
    unknown_fields = set(data) - allowed_fields
    if unknown_fields:
        return error_response('فیلدهای درخواست معتبر نیستند.', details={'fields': sorted(unknown_fields)})
    for field in {'notifications_enabled', 'show_low_stock'} & data.keys():
        if not isinstance(data[field], bool):
            return error_response(f'مقدار {field} باید درست یا نادرست باشد.')
        setattr(settings, field, data[field])
    if 'low_stock_threshold' in data:
        try:
            threshold = parse_integer(data['low_stock_threshold'])
        except (TypeError, ValueError):
            return error_response('حد موجودی کم باید عدد صحیح باشد.')
        if not 0 <= threshold <= 100000:
            return error_response('حد موجودی کم باید بین ۰ و ۱۰۰۰۰۰ باشد.')
        settings.low_stock_threshold = threshold
    settings.save()
    return JsonResponse(
        {
            'notifications_enabled': settings.notifications_enabled,
            'show_low_stock': settings.show_low_stock,
            'low_stock_threshold': settings.low_stock_threshold,
        }
    )
