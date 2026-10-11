from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/dashboard/', views.dashboard_summary, name='dashboard-summary'),
    path('api/products/', views.products, name='products'),
    path('api/products/<int:product_id>/', views.product_detail, name='product-detail'),
    path('api/stock/', views.reduce_stock, name='reduce-stock'),
    path('api/stock/increase/', views.increase_stock, name='increase-stock'),
    path('api/sales/', views.sales, name='sales'),
    path('api/settings/', views.store_settings, name='store-settings'),
]
