from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("collection", args=[self.slug])


class Product(models.Model):
    category = models.ForeignKey(
        Category, related_name="products", on_delete=models.CASCADE, null=True, blank=True
    )
    name = models.CharField(max_length=250)
    slug = models.SlugField(max_length=250, unique=True)
    brand = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tags = models.CharField(max_length=500, blank=True)
    colors = models.CharField(
        max_length=300,
        blank=True,
        help_text="Comma-separated colour names in stock order, e.g. Black, Dark Brown, Caramel",
    )
    stock = models.PositiveIntegerField(default=50)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("product_detail", args=[self.slug])

    @property
    def on_sale(self):
        return self.compare_at_price and self.compare_at_price > self.price

    @property
    def primary_image(self):
        return self.images.first()

    @property
    def discount_percent(self):
        if self.on_sale:
            return int(round((self.compare_at_price - self.price) / self.compare_at_price * 100))
        return 0


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    src = models.URLField(max_length=500, blank=True)
    image = models.ImageField(upload_to="products/", null=True, blank=True)
    alt = models.CharField(max_length=250, blank=True)
    position = models.PositiveIntegerField(default=0)
    bg_luma = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Mean brightness of the pixels around the photo edge, 0-255. Measured by the "
                  "tag_image_backgroups command; ~225+ means a plain white studio backdrop.",
    )
    band_ready = models.BooleanField(
        default=True,
        help_text="The bag alone on a plain backdrop: no model or hands, no second item, no watermark "
                  "strip. The Trending band only uses photos with this ticked; untick to bench a photo.",
    )

    class Meta:
        ordering = ["position"]

    @property
    def url(self):
        if self.image:
            return self.image.url
        return self.src


class Promo(models.Model):
    code = models.CharField(max_length=30, unique=True)
    percent_off = models.PositiveIntegerField(default=0)
    amount_off = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.code

    def usable(self):
        from django.utils import timezone
        return self.is_active and (self.expires_at is None or self.expires_at > timezone.now())

    def discount_for(self, subtotal):
        if self.amount_off is not None:
            return min(self.amount_off, subtotal)
        return (subtotal * self.percent_off / 100).quantize(Decimal("0.01"))


class Order(models.Model):
    PAYMENT_METHODS = [("mpesa", "M-Pesa"), ("cod", "Cash on delivery")]
    PAYMENT_STATUSES = [("pending", "Awaiting payment"), ("paid", "Paid"), ("cod", "Pay on delivery")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    address = models.CharField(max_length=250)
    city = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    reference = models.CharField(max_length=20, unique=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    promo_code = models.CharField(max_length=30, blank=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default="mpesa")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUSES, default="pending")
    mpesa_reference = models.CharField(max_length=30, blank=True)
    checkout_request_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.reference


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=250)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
