import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from store.models import Category, Product, ProductImage, Promo


class Command(BaseCommand):
    help = "Seed the store with handbag products from products_feed.json"

    def handle(self, *args, **opts):
        feed = json.loads(
            (Path(__file__).resolve().parents[3] / "products_feed.json").read_text(encoding="utf-8")
        )
        handbags, _ = Category.objects.get_or_create(
            name="Handbags", defaults={"slug": "handbags"}
        )
        count = 0
        for p in feed["products"]:
            name = p["title"]
            slug = p["handle"]
            variant = p["variants"][0]
            price = float(variant["price"])
            compare = variant.get("compare_at_price")
            compare = float(compare) if compare else None
            description = re.sub(r"<[^>]+>", " ", p.get("body_html") or "")
            description = " ".join(description.split())
            product, created = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "price": price,
                    "compare_at_price": compare,
                    "brand": p.get("vendor") or "Denri",
                    "tags": ", ".join(p.get("tags", [])),
                    "category": handbags,
                    "is_active": True,
                },
            )
            product.images.all().delete()
            for i, img in enumerate(p.get("images", [])):
                ProductImage.objects.create(
                    product=product,
                    src=img["src"],
                    alt=img.get("alt") or name,
                    position=i,
                )
            count += 1
        Promo.objects.get_or_create(code="DENRI10", defaults={"percent_off": 10, "is_active": True})
        # The superuser is never seeded with a hardcoded password — a literal here would end up in
        # the public repo. Create one with: python manage.py createsuperuser
        self.stdout.write(self.style.SUCCESS(f"Seeded {count} products"))


import json
import re
