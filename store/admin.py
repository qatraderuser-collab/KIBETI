from django.contrib import admin

from store.models import Category, Order, OrderItem, Product, ProductImage, Promo


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "src", "alt", "position", "bg_luma", "band_ready")
    readonly_fields = ("bg_luma",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "compare_at_price", "stock", "brand", "category", "is_active")
    list_editable = ("stock",)
    list_filter = ("category", "is_active")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "city", "subtotal", "discount", "total", "payment_method", "payment_status", "created_at")
    list_filter = ("payment_status", "payment_method", "city")
    search_fields = ("reference", "full_name", "phone")
    inlines = [OrderItemInline]


@admin.register(Promo)
class PromoAdmin(admin.ModelAdmin):
    list_display = ("code", "percent_off", "amount_off", "is_active", "expires_at")
    list_editable = ("is_active",)


admin.site.register(Category)
