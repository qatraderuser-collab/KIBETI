from django.contrib import admin
from django.utils.html import format_html

from store.models import Category, Order, OrderItem, Product, ProductImage, Promo

admin.site.site_header = "Zuri Luxee admin"
admin.site.site_title = "Zuri Luxee admin"
admin.site.index_title = "What would you like to do?"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "src", "alt", "position", "bg_luma", "band_ready")
    readonly_fields = ("bg_luma",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("photo", "name", "price", "stock", "category", "is_active")
    list_display_links = ("photo", "name")
    list_editable = ("price", "stock", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "brand")
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 30
    inlines = [ProductImageInline]
    fieldsets = (
        (None, {"fields": ("name", "category", "price", "compare_at_price", "stock", "is_active")}),
        ("Details", {"fields": ("description", "brand", "colors"), "classes": ("collapse",)}),
        ("Advanced", {"fields": ("slug", "tags"), "classes": ("collapse",)}),
    )

    @admin.display(description="")
    def photo(self, obj):
        img = obj.primary_image
        return format_html('<img class="thumb-sm" src="{}" alt="">', img.url) if img else "—"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "phone", "city", "total", "payment_method", "status", "created_at")
    list_filter = ("payment_status", "payment_method", "city")
    search_fields = ("reference", "full_name", "phone")
    date_hierarchy = "created_at"
    actions = ["mark_paid"]
    inlines = [OrderItemInline]
    readonly_fields = ("reference", "created_at", "subtotal", "discount", "total", "promo_code", "checkout_request_id")
    fieldsets = (
        ("Order", {"fields": ("reference", "created_at", "payment_method", "payment_status", "mpesa_reference")}),
        ("Customer", {"fields": ("full_name", "phone", "email", "city", "address", "notes")}),
        ("Amounts", {"fields": ("subtotal", "discount", "promo_code", "total")}),
    )

    @admin.display(description="Payment", ordering="payment_status")
    def status(self, obj):
        return format_html(
            '<span class="status-pill status-{}">{}</span>', obj.payment_status, obj.get_payment_status_display()
        )

    @admin.action(description="Mark selected orders as paid")
    def mark_paid(self, request, queryset):
        n = queryset.update(payment_status="paid")
        self.message_user(request, f"{n} order(s) marked as paid.")


@admin.register(Promo)
class PromoAdmin(admin.ModelAdmin):
    list_display = ("code", "percent_off", "amount_off", "is_active", "expires_at")
    list_editable = ("is_active",)


admin.site.register(Category)
