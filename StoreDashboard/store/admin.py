from django.contrib import admin

from .models import InventoryMovement, Product, Sale, StoreSettings


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'updated_at')
    list_filter = ('category',)
    search_fields = ('name', 'description')
    readonly_fields = ('stock',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'customer_name',
        'product',
        'quantity',
        'status',
        'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = ('order_number', 'customer_name', 'product__name')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ('product', 'movement_type', 'quantity', 'reason', 'created_at')
    list_filter = ('movement_type', 'created_at')
    search_fields = ('product__name', 'reason', 'note')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ('notifications_enabled', 'show_low_stock', 'low_stock_threshold')

    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
