from decimal import Decimal

from store.models import Product


class Cart:
    def __init__(self, request):
        self.request = request
        self.session = request.session
        cart = self.session.get("cart")
        if cart is None:
            cart = self.session["cart"] = {}
        self.cart = cart

    def add(self, product, quantity=1):
        key = str(product.id)
        if key in self.cart:
            self.cart[key]["quantity"] += quantity
        else:
            self.cart[key] = {"quantity": quantity}
        self.save()

    def set_quantity(self, product_id, quantity):
        key = str(product_id)
        if key not in self.cart:
            return
        if quantity < 1:
            del self.cart[key]
        else:
            self.cart[key]["quantity"] = quantity
        self.save()

    def remove(self, product_id):
        self.cart.pop(str(product_id), None)
        self.save()

    def clear(self):
        self.cart = {}
        self.save()

    def save(self):
        self.session["cart"] = self.cart
        self.session.modified = True

    def __iter__(self):
        product_ids = list(self.cart.keys())
        products = Product.objects.filter(id__in=product_ids, is_active=True)
        product_map = {str(p.id): p for p in products}
        items = []
        for pid in product_ids:
            product = product_map.get(pid)
            if not product:
                continue
            quantity = self.cart[pid]["quantity"]
            line_total = product.price * quantity
            item = {
                "product": product,
                "quantity": quantity,
                "line_total": line_total,
            }
            self.cart[pid]["line_total"] = str(line_total)
            items.append(item)
        self.save()
        return iter(items)

    @property
    def item_count(self):
        return sum(item["quantity"] for item in self.cart.values())

    @property
    def subtotal(self):
        return sum((item["line_total"] for item in self), Decimal("0.00"))
