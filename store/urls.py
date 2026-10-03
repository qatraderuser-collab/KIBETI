from django.urls import path

from store import views

urlpatterns = [
    path("", views.home, name="home"),
    path("collections/", views.collection, name="collection_all"),
    path("collections/<slug:category_slug>/", views.collection, name="collection"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/promo/", views.promo_preview, name="promo_preview"),
    path("orders/<str:reference>/pay/", views.order_payment, name="order_payment"),
    path("orders/<str:reference>/pay/status/", views.order_payment_status, name="order_payment_status"),
    path("orders/<str:reference>/receipt/", views.order_receipt, name="order_receipt"),
    # Safaricom posts here with no auth header, so the secret path segment is the credential.
    # The path must stay outside any login gate, and the whole URL is what you register as CallBackURL.
    path("mpesa/callback/<str:callback_secret>/", views.mpesa_callback, name="mpesa_callback"),
    path("account/", views.account, name="account"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
