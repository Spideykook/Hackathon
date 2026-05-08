"""
chatbot/management/commands/seed_demo.py

Populates the DB with sample products and support docs so you can test
the RAG pipeline immediately without manual data entry.

Usage:
    python manage.py seed_demo
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify


CATEGORIES = ["Dresses", "Tops", "Bottoms", "Outerwear", "Activewear"]

PRODUCTS = [
    {
        "name": "Midnight Wrap Dress",
        "brand": "Studio Eve",
        "category": "Dresses",
        "description": "An elegant wrap-style midi dress in deep midnight black. Perfect for dinner dates and evening events.",
        "price": "54.99",
        "gender": "W",
        "sizes_available": ["XS", "S", "M", "L", "XL"],
        "colors": ["Black", "Navy"],
        "tags": ["dress", "elegant", "midi", "evening", "wrap"],
        "stock": 42,
        "sku": "EVE-WRP-001",
    },
    {
        "name": "Floral Sundress",
        "brand": "Bloom Co",
        "category": "Dresses",
        "description": "A light, breezy floral sundress made from 100% cotton. Ideal for summer days.",
        "price": "38.99",
        "sale_price": "29.99",
        "gender": "W",
        "sizes_available": ["XS", "S", "M", "L"],
        "colors": ["Pink Floral", "Blue Floral", "Yellow Floral"],
        "tags": ["dress", "floral", "summer", "casual", "cotton", "sundress"],
        "stock": 88,
        "sku": "BLM-SUN-002",
    },
    {
        "name": "Classic Slim Jeans",
        "brand": "DenimLab",
        "category": "Bottoms",
        "description": "Slim-fit denim jeans with a touch of stretch for all-day comfort. A wardrobe staple.",
        "price": "64.99",
        "gender": "U",
        "sizes_available": ["28", "30", "32", "34", "36"],
        "colors": ["Indigo", "Black", "Light Wash"],
        "tags": ["jeans", "denim", "slim", "casual", "everyday"],
        "stock": 120,
        "sku": "DNM-SLM-003",
    },
    {
        "name": "Oversized Cotton Tee",
        "brand": "Basics+",
        "category": "Tops",
        "description": "A relaxed-fit oversized T-shirt in premium combed cotton. Available in a range of muted tones.",
        "price": "22.00",
        "gender": "U",
        "sizes_available": ["S", "M", "L", "XL", "XXL"],
        "colors": ["White", "Stone", "Sage", "Black"],
        "tags": ["tshirt", "casual", "oversized", "basics", "cotton", "unisex"],
        "stock": 200,
        "sku": "BAS-TEE-004",
    },
    {
        "name": "Quilted Winter Jacket",
        "brand": "NorthWard",
        "category": "Outerwear",
        "description": "A warm quilted jacket with down-alternative fill. Windproof exterior, packable design.",
        "price": "119.00",
        "sale_price": "89.00",
        "gender": "U",
        "sizes_available": ["XS", "S", "M", "L", "XL", "XXL"],
        "colors": ["Forest Green", "Charcoal", "Burgundy"],
        "tags": ["jacket", "winter", "warm", "quilted", "packable", "outerwear"],
        "stock": 55,
        "sku": "NWD-QJK-005",
    },
    {
        "name": "High-Rise Yoga Leggings",
        "brand": "FlexForm",
        "category": "Activewear",
        "description": "Four-way stretch yoga leggings with a high-rise waistband and hidden pocket. Moisture-wicking fabric.",
        "price": "48.00",
        "gender": "W",
        "sizes_available": ["XS", "S", "M", "L", "XL"],
        "colors": ["Black", "Midnight Blue", "Olive"],
        "tags": ["leggings", "yoga", "activewear", "gym", "stretch", "high-rise"],
        "stock": 95,
        "sku": "FLX-YGL-006",
    },
    {
        "name": "Linen Blazer",
        "brand": "Studio Eve",
        "category": "Outerwear",
        "description": "A tailored single-button linen blazer, perfect for smart-casual office looks or summer evenings.",
        "price": "84.99",
        "gender": "W",
        "sizes_available": ["XS", "S", "M", "L"],
        "colors": ["Cream", "Dusty Rose", "Navy"],
        "tags": ["blazer", "linen", "formal", "office", "summer", "tailored"],
        "stock": 33,
        "sku": "EVE-BLZ-007",
    },
    {
        "name": "Men's Chino Trousers",
        "brand": "Basics+",
        "category": "Bottoms",
        "description": "Straight-cut chino trousers in cotton-twill. Smart-casual versatility.",
        "price": "49.99",
        "gender": "M",
        "sizes_available": ["30", "32", "34", "36", "38"],
        "colors": ["Khaki", "Navy", "Olive", "Stone"],
        "tags": ["chinos", "trousers", "men", "smart-casual", "office"],
        "stock": 70,
        "sku": "BAS-CHN-008",
    },
]

SUPPORT_CATEGORIES = ["Returns & Exchanges", "Shipping", "Sizing", "Payments", "General"]

SUPPORT_DOCS = [
    {
        "title":    "Return & Refund Policy",
        "category": "Returns & Exchanges",
        "doc_type": "policy",
        "question": "",
        "content":  (
            "We accept returns within 30 days of delivery for unworn, unwashed items with original tags attached. "
            "To initiate a return, visit our Returns Portal and enter your order number. "
            "Refunds are issued to the original payment method within 5–7 business days of us receiving the item. "
            "Sale items marked 'Final Sale' cannot be returned or exchanged."
        ),
        "keywords": "return, refund, exchange, 30 days, unworn",
    },
    {
        "title":    "How do I exchange an item for a different size?",
        "category": "Returns & Exchanges",
        "doc_type": "faq",
        "question": "How do I exchange an item for a different size or color?",
        "content":  (
            "To exchange an item, visit our Returns Portal and select 'Exchange' instead of 'Refund'. "
            "Choose your new size or color, and we'll ship the replacement once we receive your original item. "
            "Exchanges are free of charge for standard sizes. If your desired size is out of stock, "
            "you'll receive a store credit instead."
        ),
        "keywords": "exchange, size, different size, swap",
    },
    {
        "title":    "Shipping Times & Costs",
        "category": "Shipping",
        "doc_type": "shipping",
        "question": "",
        "content":  (
            "Standard Shipping (5–7 business days): Free on orders over $50, otherwise $4.99. "
            "Express Shipping (2–3 business days): $12.99. "
            "Overnight Shipping: $24.99 (order by 12pm EST). "
            "International Shipping: available to 40+ countries. Rates calculated at checkout. "
            "Delivery times for international orders are 7–14 business days. "
            "All orders are processed within 1–2 business days."
        ),
        "keywords": "shipping, delivery, standard, express, overnight, international, free shipping",
    },
    {
        "title":    "How do I track my order?",
        "category": "Shipping",
        "doc_type": "faq",
        "question": "How can I track where my order is?",
        "content":  (
            "Once your order is shipped, you'll receive a confirmation email with a tracking number. "
            "You can track your order using this number on our website under 'Track Order', "
            "or directly on the carrier's website (UPS, FedEx, or USPS depending on your region). "
            "Please allow 24 hours for tracking information to update after your shipping confirmation email."
        ),
        "keywords": "track, tracking, order status, shipped, where is my order",
    },
    {
        "title":    "Size Guide",
        "category": "Sizing",
        "doc_type": "guide",
        "question": "How do I find my size?",
        "content":  (
            "Our standard size chart: XS (US 0–2, Bust 32–33\"), S (US 4–6, Bust 34–35\"), "
            "M (US 8–10, Bust 36–37\"), L (US 12–14, Bust 38–40\"), XL (US 16, Bust 41–43\"). "
            "For jeans and bottoms, sizes refer to waist measurement in inches. "
            "If you're between sizes, we recommend sizing up for a relaxed fit or sizing down for a fitted look. "
            "All measurements are listed in the product description as well."
        ),
        "keywords": "size, sizing, size chart, measurements, XS, S, M, L, XL, fit",
    },
    {
        "title":    "Accepted Payment Methods",
        "category": "Payments",
        "doc_type": "faq",
        "question": "What payment methods do you accept?",
        "content":  (
            "We accept Visa, Mastercard, American Express, PayPal, Apple Pay, Google Pay, "
            "and Shop Pay. All transactions are encrypted and processed securely. "
            "We do not store your full card details. For international orders, "
            "prices are displayed in USD and converted at checkout based on your location."
        ),
        "keywords": "payment, credit card, PayPal, Apple Pay, visa, mastercard",
    },
    {
        "title":    "Care Instructions",
        "category": "General",
        "doc_type": "guide",
        "question": "How should I care for my clothing?",
        "content":  (
            "Most of our garments can be machine washed on a cold, gentle cycle. "
            "Always check the care label inside the garment for specific instructions. "
            "We recommend turning dark items inside-out to preserve color. "
            "Hang or lay flat to dry when possible — tumble dry low if needed. "
            "Do not bleach or iron directly on prints or embellishments."
        ),
        "keywords": "care, wash, laundry, machine wash, dry, iron",
    },
]


class Command(BaseCommand):
    help = "Seeds the database with demo products and support documents."

    def handle(self, *args, **options):
        from products.models import Category, Product
        from support.models import SupportCategory, SupportDocument

        self.stdout.write("Seeding categories …")
        cat_map = {}
        for name in CATEGORIES:
            obj, _ = Category.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
            cat_map[name] = obj

        self.stdout.write("Seeding products …")
        for data in PRODUCTS:
            cat = cat_map.get(data.pop("category", None))
            data["category"] = cat
            sale_price = data.pop("sale_price", None)
            obj, created = Product.objects.get_or_create(sku=data["sku"], defaults={**data, "sale_price": sale_price})
            if created:
                self.stdout.write(f"  Created: {obj.name}")
            else:
                self.stdout.write(f"  Exists:  {obj.name}")

        self.stdout.write("Seeding support categories …")
        scat_map = {}
        for i, name in enumerate(SUPPORT_CATEGORIES):
            obj, _ = SupportCategory.objects.get_or_create(name=name, defaults={"priority": i})
            scat_map[name] = obj

        self.stdout.write("Seeding support documents …")
        for data in SUPPORT_DOCS:
            cat = scat_map.get(data.pop("category", None))
            data["category"] = cat
            obj, created = SupportDocument.objects.get_or_create(
                title=data["title"], defaults=data
            )
            if created:
                self.stdout.write(f"  Created: {obj.title}")
            else:
                self.stdout.write(f"  Exists:  {obj.title}")

        self.stdout.write(self.style.SUCCESS("\nSeed complete. Now run: python manage.py rebuild_index"))
