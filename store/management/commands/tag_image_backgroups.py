"""Refresh the photo metadata the storefront relies on: backdrop brightness and whether the bag is alone in shot."""

import json
import re
import statistics
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.core.management.base import BaseCommand

from store.models import ProductImage

EDGE_SAMPLE = 3
STAGE_NOTES = Path("_zipstage")
NOTE_KEYS = sorted(STAGE_NOTES.glob("descriptions_*.json"))
# Anything in a note that means the photo is not a clean single-bag studio shot.
DISQUALIFIED_NOTE = re.compile(
    r"\b(model|woman|women|lady|person|people|hands?|fingers|arm|arms|worn|wearing|held|holding"
    r"|carrying|selfie|mannequin|shown with|watermark|stock photo|group shot|piece|set of"
    r"|infographic|callout|duplicate|low resolution)\b",
    re.I,
)
# Defects I checked on screen and the notes say nothing about. Only photos bright enough to reach the
# Trending band are listed here; darker ones cannot surface there regardless of what they show.
BENCH_BY_EYE = {
    "blush-leather-bag-set",
    "boxy-flap-top-handle-bag",
    "floral-print-satchel-set",
    "floral-quilted-rose-backpack",
    "grey-bottle-holder-daypack",
    "multi-compartment-everyday-backpack",
    "sage-green-buckle-backpack",
    "slouchy-snap-tab-tote",
    "textured-green-shoulder-tote",
}


def slugify(value):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def disqualified_slugs():
    """Product slugs whose reference-set note rules the photo out of the Trending band."""
    slugs = set()
    for path in NOTE_KEYS:
        for entry in json.loads(path.read_text(encoding="utf-8")).values():
            if DISQUALIFIED_NOTE.search(entry.get("note") or ""):
                slugs.add(slugify(entry["name"]))
    return slugs | BENCH_BY_EYE


class Command(BaseCommand):
    help = ("Measure each photo's edge brightness into ProductImage.bg_luma, and clear band_ready where the "
            "reference-set notes say the photo shows a person, a second item or a watermark.")

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Re-measure images that already have a value.")

    def handle(self, *args, **opts):
        disqualified = disqualified_slugs() if NOTE_KEYS else set()
        all_images = ProductImage.objects.exclude(image=None)
        images = all_images if opts["force"] else all_images.filter(bg_luma__isnull=True)

        measured = skipped = benched = 0
        for img in images.select_related("product"):
            path = img.image.path
            try:
                with Image.open(path) as fh:
                    rgba = fh.convert("RGBA")
                    w, h = rgba.size
                    if w < 8 or h < 8:
                        raise ValueError("image too small to sample")
                    # Sample the backdrop over white so a genuine transparent cut-out reads like a plain
                    # studio shot; for opaque photos the composite changes nothing.
                    flat = Image.new("RGBA", (w, h), (255, 255, 255, 255))
                    flat.alpha_composite(rgba)
                    fh = flat.convert("RGB")
                    pts = [
                        (EDGE_SAMPLE, EDGE_SAMPLE), (w - 1 - EDGE_SAMPLE, EDGE_SAMPLE),
                        (EDGE_SAMPLE, h - 1 - EDGE_SAMPLE), (w - 1 - EDGE_SAMPLE, h - 1 - EDGE_SAMPLE),
                        (w // 2, EDGE_SAMPLE), (w // 2, h - 1 - EDGE_SAMPLE),
                        (EDGE_SAMPLE, h // 2), (w - 1 - EDGE_SAMPLE, h // 2),
                    ]
                    ring = [sum(fh.getpixel(p)) / 3 for p in pts]
            except (OSError, ValueError, UnidentifiedImageError) as exc:
                skipped += 1
                self.stderr.write(f"skipped {path}: {exc}")
                continue

            fields = ["bg_luma"]
            img.bg_luma = round(statistics.mean(ring))
            # Only ever bench a photo, never restore one: a tick set by hand in admin survives a rerun.
            if img.band_ready and img.product.slug in disqualified:
                img.band_ready = False
                fields.append("band_ready")
                benched += 1
            img.save(update_fields=fields)
            measured += 1

        clean = all_images.filter(bg_luma__gte=225, band_ready=True).count()
        self.stdout.write(self.style.SUCCESS(
            f"measured {measured}, skipped {skipped}; {clean} band-ready studio shots, {benched} newly benched"
        ))
