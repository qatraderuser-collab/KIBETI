import json
import random
import string
from decimal import Decimal

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.paginator import Paginator
from django.db.models import F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from store import payments
from store.cart import Cart
from store.forms import CheckoutForm
from store.models import Category, Order, OrderItem, Product, ProductImage, Promo

SORT_OPTIONS = {
    "featured": ("-created_at", "id"),
    "price-asc": ("price", "id"),
    "price-desc": ("-price", "id"),
    "name": ("name",),
}


def _apply_filters(request, products):
    q = request.GET.get("q", "").strip()
    if q:
        products = products.filter(Q(name__icontains=q) | Q(description__icontains=q))
    sale = request.GET.get("sale") == "1"
    if sale:
        products = products.filter(compare_at_price__isnull=False, compare_at_price__gt=F("price"))
    instock = request.GET.get("instock") == "1"
    if instock:
        products = products.filter(stock__gt=0)
    bounds = {}
    for key, lookup in (("min", "price__gte"), ("max", "price__lte")):
        raw = request.GET.get(key, "").strip()
        bounds[key] = raw
        if raw.replace(".", "", 1).isdigit():
            products = products.filter(**{lookup: float(raw)})
    sort = request.GET.get("sort", "featured")
    products = products.order_by(*SORT_OPTIONS.get(sort, ("-created_at", "id")))
    return products, q, sale, sort, instock, bounds


def _mix_categories(queryset, limit):
    """Round-robin across categories (newest first within each) so the home page isn't one category."""
    buckets = {}
    for p in queryset.select_related("category"):
        buckets.setdefault(p.category_id, [])
        if len(buckets[p.category_id]) < limit:
            buckets[p.category_id].append(p)
    mixed = []
    lists = list(buckets.values())
    for i in range(limit):
        for lst in lists:
            if i < len(lst):
                mixed.append(lst[i])
    return mixed[:limit]


def home(request):
    products = Product.objects.filter(is_active=True).order_by("-created_at", "id")
    # Trending shows the bag on its own: only photos flagged as a single bag on a plain backdrop, and
    # the whitest of those first, since they sit closest to the tile surface and read as no background.
    first_image = ProductImage.objects.filter(product=OuterRef("pk")).order_by("position", "id")
    trending_products = (
        products.annotate(
            first_bg=Subquery(first_image.values("bg_luma")[:1]),
            first_band_ready=Subquery(first_image.values("band_ready")[:1]),
        )
        .filter(first_band_ready=True)
        .annotate(bg_rank=Coalesce("first_bg", Value(0)))
        .order_by("-bg_rank", "-created_at", "id")
    )
    tiles = []
    for p in _mix_categories(trending_products.prefetch_related("images"), 16):
        words = p.name.replace("’", "'").split()[:4]
        tiles.append({"product": p, "label": " ".join(words).strip(" |-–—,·"), "image": p.primary_image})
    capsule = [{"image": p.primary_image, "alt": p.name} for p in products.select_related("category").prefetch_related("images")[:6]]
    capsule = [c for c in capsule if c["image"]][:3]
    return render(
        request,
        "store/home.html",
        {
            "featured": _mix_categories(products, 12),
            "total": products.count(),
            "collections": Category.objects.all(),
            "trending": tiles,
            "capsule": capsule,
        },
    )


def collection(request, category_slug=None):
    category = None
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        base = category.products.filter(is_active=True)
    else:
        base = Product.objects.filter(is_active=True)
    products, q, sale, sort, instock, bounds = _apply_filters(request, base)
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "store/collection.html",
        {
            "category": category,
            "page_obj": page_obj,
            "q": q,
            "sale": "1" if sale else "",
            "instock": "1" if instock else "",
            "bounds": bounds,
            "sort": sort,
            "total": paginator.count,
            "shown": len(page_obj.object_list),
            "price_floor": base.order_by("price").values_list("price", flat=True).first(),
            "collections": Category.objects.all(),
            "sort_options": SORT_OPTIONS.keys(),
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    related = Product.objects.filter(is_active=True).exclude(id=product.id).order_by("?")[:4]
    return render(request, "store/product_detail.html", {"product": product, "related": related})


def _wants_json(request):
    return request.headers.get("x-requested-with") == "fetch"


def cart_add(request):
    if request.method != "POST":
        return redirect("collection")
    product = get_object_or_404(Product, id=request.POST.get("product_id"), is_active=True)
    quantity = max(1, min(int(request.POST.get("quantity") or 1), 99))
    cart = Cart(request)
    current = cart.cart.get(str(product.id), {}).get("quantity", 0)
    available = product.stock - current
    if available < 1:
        msg = f"Sorry, {product.name} is out of stock."
        if _wants_json(request):
            return JsonResponse({"ok": False, "message": msg}, status=409)
        request.session["cart_toast"] = {"ok": False, "message": msg}
        return redirect(request.POST.get("next") or "cart_detail")
    quantity = min(quantity, available)
    cart.add(product, quantity)
    msg = f"Added {quantity} × {product.name} to cart"
    if _wants_json(request):
        return JsonResponse({"ok": True, "message": msg, "cart_count": cart.item_count})
    request.session["cart_toast"] = {"ok": True, "message": msg}
    return redirect(request.POST.get("next") or "cart_detail")


def cart_detail(request):
    return render(request, "store/cart.html", {"cart": Cart(request)})


def cart_update(request):
    if request.method == "POST":
        cart = Cart(request)
        product_id = request.POST.get("product_id")
        if request.POST.get("action") == "remove":
            cart.remove(product_id)
        else:
            cart.set_quantity(product_id, max(1, min(int(request.POST.get("quantity") or 1), 99)))
    return redirect("cart_detail")


def _new_reference():
    return "KB" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def checkout(request):
    cart = Cart(request)
    if not cart.cart:
        return redirect("cart_detail")
    form = CheckoutForm(request.POST or None, initial={
        "full_name": getattr(request.user, "first_name", "") or "",
        "email": getattr(request.user, "email", "") or "",
    } if not request.POST else None)
    if request.method == "POST" and form.is_valid():
        payment_method = request.POST.get("payment_method", "mpesa")
        promo_code = request.POST.get("promo", "").strip().upper()
        promo = None
        if promo_code:
            promo = Promo.objects.filter(code=promo_code).first()
            if not promo or not promo.usable():
                return render(
                    request, "store/checkout.html",
                    {"form": form, "cart": cart, "promo_error": f"“{promo_code}” is not a valid or active promo code."},
                )
        subtotal = cart.subtotal
        discount = promo.discount_for(subtotal) if promo else Decimal("0.00")
        order = form.save(commit=False)
        order.user = request.user if request.user.is_authenticated else None
        order.reference = _new_reference()
        order.payment_method = payment_method
        order.subtotal = subtotal
        order.discount = discount
        order.promo_code = promo_code if promo else ""
        order.save()
        for item in cart:
            product = item["product"]
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                price=product.price,
                quantity=item["quantity"],
            )
            Product.objects.filter(id=product.id).update(stock=F("stock") - item["quantity"])
        order.total = subtotal - discount
        order.save()
        cart.clear()
        if payment_method == "cod":
            order.payment_status = "cod"
            order.save(update_fields=["payment_status"])
            return render(request, "store/order_success.html", {"order": order})
        ok, payload = payments.initiate_stk(order.phone, order.total, order.reference)
        if ok:
            order.checkout_request_id = payload
            order.save(update_fields=["checkout_request_id"])
            return redirect("order_payment", reference=order.reference)
        order.payment_status = "pending"
        order.save()
        request.session["cart_toast"] = {"ok": False, "message": f"M-Pesa prompt failed: {payload}. Pay later from My Orders."}
        return render(request, "store/order_success.html", {"order": order})
    return render(request, "store/checkout.html", {"form": form, "cart": cart})


def promo_preview(request):
    if request.method != "POST":
        return JsonResponse({"ok": False}, status=405)
    code = request.POST.get("code", "").strip().upper()
    cart = Cart(request)
    subtotal = cart.subtotal
    if not code:
        return JsonResponse({"ok": True, "discount": "0.00", "total": str(subtotal)})
    promo = Promo.objects.filter(code=code).first()
    if not promo or not promo.usable():
        return JsonResponse({"ok": False, "message": f"“{code}” is not valid."})
    discount = promo.discount_for(subtotal)
    return JsonResponse({
        "ok": True, "discount": f"{discount:.2f}", "total": f"{subtotal - discount:.2f}",
        "message": f"{promo.percent_off}% off applied" if promo.percent_off else f"KSh {promo.amount_off:,.0f} off applied",
    })


def order_payment(request, reference):
    order = get_object_or_404(Order, reference=reference)
    if order.payment_status == "paid":
        return render(request, "store/order_success.html", {"order": order})
    return render(
        request,
        "store/order_payment.html",
        {"order": order, "mpesa_mode": payments.mpesa_mode()},
    )


def order_payment_status(request, reference):
    order = get_object_or_404(Order, reference=reference)
    if order.payment_status == "paid":
        return JsonResponse({"status": "paid", "mpesa_reference": order.mpesa_reference})
    status, receipt = payments.query_stk(order.checkout_request_id)
    if status == "success":
        order.payment_status = "paid"
        order.mpesa_reference = receipt
        order.save(update_fields=["payment_status", "mpesa_reference"])
        return JsonResponse({"status": "paid", "mpesa_reference": receipt})
    if status == "failed":
        return JsonResponse({"status": "failed"})
    return JsonResponse({"status": "pending"})


def _daraja_ack(result_code, result_desc, status=200):
    """Daraja reads this envelope, so answer in its own format rather than Django's."""
    return JsonResponse(
        {"ResultCode": result_code, "ResultDesc": result_desc},
        status=status,
    )


@csrf_exempt
@require_POST
def mpesa_callback(request, callback_secret):
    """Safaricom's server-to-server confirmation, posted the moment the customer enters their PIN.

    This is the authoritative copy of the result: it lands even when the browser was closed before
    the payment page finished polling, which is why the amount and the receipt number are taken from
    the callback rather than from anything the customer's device can influence. Safaricom sends no
    auth header, so the secret in the URL path is what authenticates the caller.
    """
    if not payments.callback_authorized(callback_secret):
        return _daraja_ack(1, "Unauthorised callback", status=403)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return _daraja_ack(1, "Malformed request")

    # Sandbox nests the fields twice, production once.
    payload = body.get("Body", body).get("MpesaCallbackBody", body)
    metadata = {
        item.get("Name"): item.get("Value")
        for item in (payload.get("CallbackMetadata") or {}).get("Item", [])
    }
    checkout_id = payload.get("CheckoutRequestID", "")
    order = Order.objects.filter(checkout_request_id=checkout_id).first() if checkout_id else None
    if order is None:
        return _daraja_ack(1, "Unknown CheckoutRequestID")

    if str(payload.get("ResultCode", "")) != "0":
        # Anything else is a cancel, a timeout or a wrong PIN: leave the order awaiting payment so
        # the customer can retry from My Orders.
        return _daraja_ack(1, payload.get("ResultDesc") or "Payment not completed")

    amount = metadata.get("Amount")
    if amount is not None:
        try:
            paid = Decimal(str(amount)).quantize(Decimal("0.01"))
        except (ArithmeticError, TypeError, ValueError):
            return _daraja_ack(1, "Unreadable Amount")
        if paid != order.total:
            return _daraja_ack(1, "Amount does not match the order")

    receipt = metadata.get("MpesaReceiptNumber") or payload.get("ReceiptID") or payload.get("TransactionID") or ""
    if order.payment_status != "paid":
        order.payment_status = "paid"
        order.mpesa_reference = receipt
        order.save(update_fields=["payment_status", "mpesa_reference"])
    return _daraja_ack(0, "The service request is processed successfully.")


def order_receipt(request, reference):
    order = get_object_or_404(Order, reference=reference)
    qr = _receipt_qr(request, order)
    return render(request, "store/receipt.html", {"order": order, "qr_svg": mark_safe(qr)})


def _receipt_qr(request, order):
    import qrcode
    from qrcode.image.svg import SvgPathImage

    # The code replaces the barcode, so it has to be something a phone camera can act on: this
    # receipt's own URL. A JSON blob would just be printed as text by most scanners.
    url = request.build_absolute_uri()
    img = qrcode.make(url, image_factory=SvgPathImage, box_size=4, border=2)
    return img.to_string().decode()


@login_required
def account(request):
    return render(request, "store/account.html", {"orders": request.user.orders.all()})


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("account")
    else:
        form = UserCreationForm()
    return render(request, "store/register.html", {"form": form})


def login_view(request):
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get("next") or "account")
    return render(request, "store/login.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("home")


def dashboard(request):
    if not request.user.is_staff:
        return redirect("home")
    orders = Order.objects.all()
    paid = orders.filter(payment_status="paid")
    revenue = paid.aggregate(s=Sum("total"))["s"] or 0
    recent = orders.order_by("-created_at")[:8]
    low_stock = Product.objects.filter(stock__lte=10).order_by("stock")[:10]
    daily = (
        orders.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Sum("total"))
        .order_by("day")[:14]
    )
    max_day = max((d["count"] for d in daily), default=0) or 1
    return render(
        request,
        "store/dashboard.html",
        {
            "order_count": orders.count(),
            "pending_count": orders.filter(payment_status="pending").count(),
            "product_count": Product.objects.count(),
            "customer_count": orders.filter(user__isnull=False).values("user").distinct().count(),
            "revenue": revenue,
            "recent": recent,
            "low_stock": low_stock,
            "daily": [{"day": d["day"], "pct": float(d["count"]) / float(max_day) * 100, "amount": d["count"]} for d in daily],
        },
    )
