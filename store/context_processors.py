from store.cart import Cart
from store.models import Category


def store_nav(request):
    toast = request.session.pop("cart_toast", None)
    return {
        "cart_count": Cart(request).item_count,
        "nav_collections": Category.objects.all(),
        "cart_toast": toast,
    }
