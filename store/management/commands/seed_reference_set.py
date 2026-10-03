import hashlib
import json
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from store.models import Category, Product, ProductImage

MARKER = "zuri-luxee-set"
DESC_FILES = (
    "descriptions_handbags_a.json",
    "descriptions_handbags_b.json",
    "descriptions_purses.json",
    "descriptions_backpacks.json",
)
PRICE_BANDS = {
    "Handbags": (2600, 8900),
    "Purses": (1200, 3900),
    "Backpacks": (3200, 6900),
}
FOLDER_CATEGORY = {"handbags": "Handbags", "purses": "Purses", "backpacks": "Backpacks"}
PURSE_WORDS = re.compile(r"clutch|wristlet|pouch|wallet|coin", re.I)
BACKPACK_WORDS = re.compile(r"backpack|back pack|daypack|rucksack", re.I)


def slugify(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:70] or "item"


class Command(BaseCommand):
    help = "Seed products from the Zuri Luxee reference image set (images + per-image descriptions)"

    def add_arguments(self, parser):
        parser.add_argument("--stage", default=str(Path(settings.BASE_DIR) / "_zipstage"))
        parser.add_argument("--retire-old", action="store_true", help="Deactivate non-reference products")

    def handle(self, *args, **opts):
        stage = Path(opts["stage"])
        meta_path = stage / "_meta.json"
        if not meta_path.exists():
            raise CommandError(f"{meta_path} is missing - extract the reference zip and verify hashes first")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        descriptions = {}
        for name in DESC_FILES:
            path = stage / name
            if not path.exists():
                raise CommandError(f"missing descriptions file: {path}")
            for key, value in json.loads(path.read_text(encoding="utf-8")).items():
                if key in descriptions:
                    raise CommandError(f"duplicate description key {key}")
                descriptions[key] = value
        missing = set(meta) - set(descriptions)
        if missing:
            raise CommandError(f"images without a description: {sorted(missing)[:5]}")

        categories = {c.name: c for c in Category.objects.all()}
        media_dir = Path(settings.MEDIA_ROOT) / "products" / "zuri-luxee"
        media_dir.mkdir(parents=True, exist_ok=True)
        used_slugs = set(Product.objects.exclude(tags__contains=MARKER).values_list("slug", flat=True))
        keep_slugs = set()
        made = skipped = 0
        for rel, info in sorted(meta.items()):
            desc = descriptions[rel]
            folder = rel.split("/")[0]
            if not desc.get("usable"):
                skipped += 1
                self.stdout.write(self.style.WARNING(f"skip (not a product photo): {rel} - {desc.get('note', '')[:70]}"))
                continue
            if desc.get("duplicate_of"):
                skipped += 1
                self.stdout.write(self.style.WARNING(f"skip (same photo as {desc['duplicate_of']}): {rel}"))
                continue

            source = stage / Path(*rel.split("/"))
            raw = source.read_bytes()
            if hashlib.sha256(raw).hexdigest() != info["sha"]:
                raise CommandError(f"staged file no longer matches its hash: {rel}")

            title = desc["name"].strip()
            text = f"{title} {desc['description']}"
            if BACKPACK_WORDS.search(text):
                cat_name = "Backpacks"
            elif PURSE_WORDS.search(title):
                cat_name = "Purses"
            else:
                cat_name = FOLDER_CATEGORY[folder]
            if cat_name not in categories:
                categories[cat_name] = Category.objects.create(name=cat_name, slug=slugify(cat_name))

            seed = int(info["sha"][:8], 16)
            low, high = PRICE_BANDS[cat_name]
            price = round((low + (seed % (high - low))) / 50) * 50
            compare = round(price * 1.35 / 50) * 50 if seed % 4 == 0 else None
            stock = 15 + (seed >> 8) % 46

            base = slugify(title)
            slug, suffix = base, 2
            while slug in used_slugs:
                slug = f"{base}-{suffix}"
                suffix += 1
            used_slugs.add(slug)
            keep_slugs.add(slug)

            stored = f"products/zuri-luxee/{folder}-{slug}{Path(rel).suffix}"
            target = Path(settings.MEDIA_ROOT) / stored
            target.write_bytes(raw)
            if hashlib.sha256(target.read_bytes()).hexdigest() != info["sha"]:
                raise CommandError(f"copy changed bytes: {rel}")

            product, _ = Product.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": title,
                    "category": categories[cat_name],
                    "brand": "Zuri Luxee",
                    "description": desc["description"].strip(),
                    "price": price,
                    "compare_at_price": compare,
                    "colors": ", ".join(dict.fromkeys(c.strip() for c in desc.get("colour_names", []))),
                    "tags": ", ".join(desc.get("style_tags", []) + ["Bags in Kenya", MARKER]),
                    "stock": stock,
                    "is_active": True,
                },
            )
            product.images.exclude(image=stored).delete()
            ProductImage.objects.update_or_create(
                product=product,
                image=stored,
                defaults={"alt": f"{title} - {cat_name.lower()} photo", "position": 0, "src": ""},
            )
            made += 1

        stale = Product.objects.filter(tags__contains=MARKER).exclude(slug__in=keep_slugs)
        if stale:
            self.stdout.write(self.style.WARNING(f"removing {stale.count()} reference products no longer in the set"))
            stale.delete()

        if opts["retire_old"]:
            retired = Product.objects.exclude(tags__contains=MARKER).update(is_active=False)
            self.stdout.write(self.style.SUCCESS(f"deactivated {retired} earlier products"))

        self.stdout.write(self.style.SUCCESS(f"seeded {made} products, skipped {skipped} images"))
