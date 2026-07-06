#!/usr/bin/env python
"""
Makwanpur Mart — Production Seed Script
Run: python manage.py shell < seed.py
  or: python manage.py shell
      >>> exec(open('seed.py').read())
Creates: categories, vendors (verified), products (approved), users, addresses, reviews, coupons
All data is Hetauda / Makwanpur authentic, no dummy lorem ipsum.
"""
import os, django, random
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from apps.accounts.models import User, VendorProfile, Address, SellerReview
from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Review
from apps.orders.models import Coupon, Order, OrderItem
from django.contrib.auth import get_user_model

User = get_user_model()

print("🌱 Makwanpur Mart — Seeding Hetauda Bazaar (Makwanpur District, Nepal)")
print("="*70)

# Clean slate (dev only)
if input("Wipe existing catalog data? (yes/NO): ").lower() == 'yes':
    print("Wiping...")
    Review.objects.all().delete()
    ProductImage.objects.all().delete()
    ProductVariant.objects.all().delete()
    Product.objects.all().delete()
    SellerReview.objects.all().delete()
    VendorProfile.objects.all().delete()
    Category.objects.all().delete()
    # keep Users? optionally wipe vendors
    User.objects.filter(role__in=['vendor','rider']).delete()
    print("Wiped.")

# 1. Categories — Hetauda authentic hierarchy
categories_data = [
    ("Fashion & Clothing", "fashion", "👗", None, [
        ("Women's Kurtas & Sets", "kurtas", "👘"),
        ("Traditional Sarees", "sarees", "🥻"),
        ("Men's Daura Suruwal", "mens", "👔"),
        ("Kids & Infants", "kids", "👶"),
    ]),
    ("Beauty & Cosmetics", "beauty", "💄", None, [
        ("Skincare & Face Oils", "skincare", "🧴"),
        ("Ayurvedic Haircare", "haircare", "🌿"),
        ("Makeup", "makeup", "💋"),
    ]),
    ("Local Food & Snacks", "food", "🥟", None, [
        ("Gundruk & Fermented", "gundruk", "🥬"),
        ("Sweets & Bakery", "sweets", "🍬"),
        ("Tea & Coffee", "tea", "☕"),
    ]),
    ("Handicrafts", "handicrafts", "🧶", None, [
        ("Lokta Paper", "lokta", "📜"),
        ("Dhaka Weave", "dhaka", "🧣"),
        ("Bamboo Craft", "bamboo", "🎋"),
    ]),
    ("Electronics", "electronics", "📱", None, []),
    ("Home & Kitchen", "home", "🏠", None, []),
]

cat_map = {}
for name, slug, icon_emoji, parent, children in categories_data:
    cat, created = Category.objects.get_or_create(
        slug=slug,
        defaults=dict(name=name, is_active=True)
    )
    cat_map[slug] = cat
    if created: print(f"  + Category: {name}")
    for cname, cslug, cicon in children:
        child, c_created = Category.objects.get_or_create(
            slug=cslug,
            defaults=dict(name=cname, parent=cat, is_active=True)
        )
        cat_map[cslug] = child
        if c_created: print(f"    ↳ {cname}")

# 2. Vendors — verified Hetauda shops
vendors_data = [
    {
        "email": "shrestha cloth@makwanpur.test",
        "shop_name": "Shrestha Cloth Store",
        "shop_slug": "shrestha-cloth-store",
        "category": "fashion",
        "ward": 4, "municipality": "Hetauda",
        "landmark": "Opposite Pashupati Temple Gate, Main Bazaar Road",
        "description": "35 years serving Hetauda — authentic handloom cotton, Dhaka, party wear. Family-run since 1991.",
        "verified": True,
        "rating": Decimal("4.7"), "sales": 187, "reviews": 42,
    },
    {
        "email": "himalayanbeauty@makwanpur.test",
        "shop_name": "Himalayan Beauty Hub",
        "shop_slug": "himalayan-beauty-hub",
        "category": "beauty",
        "ward": 2, "municipality": "Hetauda",
        "landmark": "Bank Road, near Siddhartha Bank",
        "description": "Organic Ayurvedic skincare — Kumkumadi, neem, aloe vera. Dermatologist consulted.",
        "verified": True,
        "rating": Decimal("4.5"), "sales": 124, "reviews": 31,
    },
    {
        "email": "makwanpurhandloom@makwanpur.test",
        "shop_name": "Makwanpur Handloom Cooperative",
        "shop_slug": "makwanpur-handloom",
        "category": "handicrafts",
        "ward": 10, "municipality": "Hetauda",
        "landmark": "Industrial District, Handloom Center",
        "description": "Women's cooperative — Palpali Dhaka, Lokta paper, bamboo craft. Fair trade certified.",
        "verified": True,
        "rating": Decimal("4.8"), "sales": 96, "reviews": 28,
    },
    {
        "email": "radhakrishna@makwanpur.test",
        "shop_name": "Radha Krishna Collection",
        "shop_slug": "radha-krishna-collection",
        "category": "fashion",
        "ward": 4, "municipality": "Hetauda",
        "landmark": "Main Bazaar, Ward 4",
        "description": "Festive sarees, lehengas, bridal wear — Silk, Banarasi, Dhaka mix.",
        "verified": True,
        "rating": Decimal("4.4"), "sales": 73, "reviews": 19,
    },
    {
        "email": "thahaorganics@makwanpur.test",
        "shop_name": "Thaha Organic Foods",
        "shop_slug": "thaha-organic-foods",
        "category": "food",
        "ward": 7, "municipality": "Thaha",
        "landmark": "Thaha Bazar",
        "description": "Gundruk, sinki, churpi, local honey — chemical-free Makwanpur produce.",
        "verified": False,
        "rating": Decimal("4.2"), "sales": 34, "reviews": 8,
    },
    {
        "email": "helectronics@makwanpur.test",
        "shop_name": "Hetauda Electronics Hub",
        "shop_slug": "hetauda-electronics-hub",
        "category": "electronics",
        "ward": 5, "municipality": "Hetauda",
        "landmark": "Milan Chowk",
        "description": "Mobiles, accessories, home appliances — authorized dealer.",
        "verified": True,
        "rating": Decimal("4.3"), "sales": 58, "reviews": 15,
    },
]

vendors = {}
for v in vendors_data:
    email = v["email"].replace(" ", "")
    user, u_created = User.objects.get_or_create(
        email=email,
        defaults=dict(
            username=slugify(v["shop_name"]).replace("-", "")[:30],
            phone_number=f"+97798{random.randint(400000000, 499999999)}",
            role=User.Role.VENDOR,
            is_active=True,
            is_phone_verified=True,
            first_name=v["shop_name"].split()[0],
        )
    )
    if u_created:
        user.set_password("vendor12345")
        user.save()
    cat = cat_map.get(v["category"])
    vendor, created = VendorProfile.objects.get_or_create(
        user=user,
        defaults=dict(
            shop_name=v["shop_name"],
            shop_slug=v["shop_slug"],
            category=cat,
            shop_municipality=v["municipality"],
            shop_ward_number=v["ward"],
            shop_landmark=v["landmark"],
            shop_full_address=f"{v['landmark']}, Ward {v['ward']}, {v['municipality']}, Makwanpur",
            shop_description=v["description"],
            verification_status=VendorProfile.VerificationStatus.VERIFIED if v["verified"] else VendorProfile.VerificationStatus.PENDING,
            verified_at=timezone.now() - timedelta(days=random.randint(30, 300)) if v["verified"] else None,
            average_rating=v["rating"],
            total_sales=v["sales"],
            total_reviews_count=v["reviews"],
            trust_score= min(30 + int(float(v["rating"])*12) + v["sales"]//10 + min(v["reviews"],10), 100) if v["verified"] else 45,
            is_trusted_seller = v["verified"] and float(v["rating"]) >= 4.2 and v["sales"] >= 50,
            payout_method="esewa",
            payout_account_details="eSewa ID: 98XXXXXXXX (encrypted in prod)",
            return_window_days=3,
            return_policy_text="3-Day Doorstep Replacement: size/fit issues or manufacturing defects — rider pickup free within Hetauda wards 1-19. Exchange at Ward {} physical stall.".format(v["ward"]),
            accepts_returns=True,
            refund_method="both",
        )
    )
    vendors[v["shop_slug"]] = vendor
    print(f"{'✓' if v['verified'] else '⏳'} Vendor: {vendor.shop_name} — {vendor.average_rating}★ — Trust {vendor.trust_score}/100 — {vendor.location_display}")

# 3. Products — approved, with transparent pricing, moderation passed
products_data = [
    # Shrestha Cloth Store
    dict(vendor="shrestha-cloth-store", name="Traditional Handloom Cotton Kurta Set with Dupatta", category="kurtas", price=2200, discounted_price=1850, stock=24, sku="SCC-KURTA-M-001", desc="Pure Hetauda handloom cotton, pre-shrunk, 3-piece kurta salwar dupatta. Sizes M/L/XL. Color: maroon, navy, mustard.", variants=[("M","Maroon",8,None),("L","Maroon",7,None),("XL","Navy",9,None)]),
    dict(vendor="shrestha-cloth-store", name="Men's Daura Suruwal – Festival White", category="mens", price=3500, discounted_price=2990, stock=12, sku="SCC-DAURA-001", desc="Nepali national dress, Dhaka topi included, tailored fit, pure cotton.", variants=[]),
    dict(vendor="shrestha-cloth-store", name="Kids Cotton Frock – Summer", category="kids", price=950, discounted_price=750, stock=30, sku="SCC-KIDS-012", desc="Breathable cotton, ages 2-8, Hetauda stitched.", variants=[("2-3Y","Pink",10,None),("4-5Y","Yellow",10,None),("6-8Y","Blue",10,None)]),
    # Himalayan Beauty Hub
    dict(vendor="himalayan-beauty-hub", name="Organic Kumkumadi Face Glow Oil – 30ml", category="skincare", price=1200, discounted_price=950, stock=40, sku="HBH-KUM-30", desc="24-karat saffron infused, cold-pressed sesame base, dermatologically tested Kathmandu lab.", variants=[]),
    dict(vendor="himalayan-beauty-hub", name="Neem-Aloe Anti-Acne Gel", category="skincare", price=650, discounted_price=None, stock=55, sku="HBH-NEEM-50", desc="Makwanpur neem + aloe, 50g, no parabens.", variants=[]),
    dict(vendor="himalayan-beauty-hub", name="Herbal Hair Strengthening Oil", category="haircare", price=800, discounted_price=720, stock=33, sku="HBH-HAIR-100", desc="Bhringraj, amla, 100ml.", variants=[]),
    # Makwanpur Handloom
    dict(vendor="makwanpur-handloom", name="Handwoven Palpali Dhaka Shawl", category="dhaka", price=1650, discounted_price=1450, stock=9, sku="MHC-DHAKA-01", desc="Women cooperative weave, 100% wool blend, 200x70cm.", variants=[("","Red",3,None),("","Green",3,None),("","Navy",3,None)]),
    dict(vendor="makwanpur-handloom", name="Lokta Paper Notebook – Handmade", category="lokta", price=450, discounted_price=380, stock=60, sku="MHC-LOKTA-NB", desc="Tree-free Lokta, 120 pages, Hetauda handmade.", variants=[]),
    dict(vendor="makwanpur-handloom", name="Bamboo Tea Tray Set", category="bamboo", price=1250, discounted_price=None, stock=18, sku="MHC-BAMBOO-TT", desc="Sustainably harvested Makwanpur bamboo, food-safe lacquer.", variants=[]),
    # Radha Krishna
    dict(vendor="radha-krishna-collection", name="Festive Silk Saree with Blouse Piece", category="sarees", price=5200, discounted_price=4500, stock=7, sku="RKC-SAREE-SILK01", desc="Art silk, zari border, includes unstitched blouse, dry clean only.", variants=[]),
    dict(vendor="radha-krishna-collection", name="Bridal Lehenga – Maroon Velvet", category="sarees", price=18500, discounted_price=15900, stock=2, sku="RKC-LEHENGA-BR", desc="Heavy embroidery, cancan included, Hetauda trial available.", variants=[]),
    # Thaha Organics
    dict(vendor="thaha-organic-foods", name="Thaha Gundruk – 500g", category="gundruk", price=350, discounted_price=300, stock=120, sku="TOF-GUND-500", desc="Sun-dried mustard leaf, traditional Thaha fermentation, no preservatives.", variants=[]),
    dict(vendor="thaha-organic-foods", name="Churpi Hard Cheese – 250g", category="gundruk", price=480, discounted_price=None, stock=80, sku="TOF-CHURPI-250", desc="Yak-cow blend, high altitude, protein rich.", variants=[]),
    # Electronics Hub
    dict(vendor="hetauda-electronics-hub", name="Redmi 13C – 6/128GB", category="electronics", price=18999, discounted_price=16999, stock=15, sku="HEH-REDMI13C", desc="NRB approved, 1yr local Hetauda warranty, free delivery ward 1-10.", variants=[("","Midnight Black",5,None),("","Sage Green",5,None),("","Glacier White",5,None)]),
    dict(vendor="hetauda-electronics-hub", name="MI Powerbank 20000mAh", category="electronics", price=3200, discounted_price=2790, stock=40, sku="HEH-PB20K", desc="18W fast charge, BIS certified.", variants=[]),
]

from django.utils.text import slugify as dj_slugify

created_products = []
for p in products_data:
    vendor = vendors.get(p["vendor"])
    if not vendor:
        continue
    category = cat_map.get(p["category"])
    slug_base = dj_slugify(f"{vendor.shop_slug}-{p['name']}")[:200]
    slug = slug_base
    counter = 1
    while Product.objects.filter(slug=slug).exists():
        slug = f"{slug_base}-{counter}"
        counter += 1
        if counter>20: break
    product, created = Product.objects.get_or_create(
        vendor=vendor,
        slug=slug,
        defaults=dict(
            category=category,
            name=p["name"],
            description=p["desc"],
            price=Decimal(str(p["price"])),
            discounted_price=Decimal(str(p["discounted_price"])) if p["discounted_price"] else None,
            stock_quantity=p["stock"],
            sku=p["sku"],
            condition=Product.Condition.NEW,
            is_active=True,
            moderation_status=Product.ModerationStatus.APPROVED,
            auto_flag_score=random.randint(0,12),
            flagged_reasons=[],
            reviewed_at=timezone.now(),
            tax_rate=Decimal("13.00"),
            platform_fee_rate=Decimal("2.00"),
        )
    )
    if created:
        # variants
        for size,color,stock,price_override in p.get("variants", []):
            ProductVariant.objects.create(
                product=product,
                size=size,
                color=color,
                stock_quantity=stock,
                price_override=Decimal(str(price_override)) if price_override else None
            )
        created_products.append(product)
        print(f"  + {product.name} — NPR {product.effective_price} — {vendor.shop_name} — {product.moderation_status}")

print(f"\n✅ Seeded {len(created_products)} new products, total live: {Product.objects.filter(is_active=True, moderation_status='approved').count()}")

# 4. Demo customer + address
cust_email = "sita.shrestha@makwanpur.test"
customer, created = User.objects.get_or_create(
    email=cust_email,
    defaults=dict(
        username="sitashrestha",
        phone_number="+9779845123456",
        role=User.Role.CUSTOMER,
        is_active=True,
        is_phone_verified=True,
        first_name="Sita", last_name="Shrestha"
    )
)
if created:
    customer.set_password("customer123")
    customer.save()
    print(f"✓ Customer: {cust_email} / customer123")

addr, _ = Address.objects.get_or_create(
    user=customer,
    label="Home",
    defaults=dict(
        full_address="Main Bazaar Road, Hetauda-4",
        landmark="Opposite Pashupati Temple Gate",
        municipality="Hetauda",
        ward_number=4,
        is_default=True,
        latitude=Decimal("27.4287"),
        longitude=Decimal("85.0320"),
    )
)

# 5. Coupons
from apps.orders.models import Coupon
now = timezone.now()
coupons = [
    ("HETAUDA10", "percentage", 10, 30),
    ("WELCOME50", "flat", 50, 15),
    ("DASHIAN25", "percentage", 15, 60),
]
for code, dtype, val, days in coupons:
    cp, created = Coupon.objects.get_or_create(
        code=code,
        defaults=dict(
            discount_type=dtype,
            value=Decimal(str(val)),
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=days),
            usage_limit=500,
            times_used=random.randint(5, 80),
            is_active=True,
        )
    )
    if created: print(f"  + Coupon {code}: {val}{'%' if dtype=='percentage' else ' NPR'}")

# 6. Seller reviews (Trust & Transparency)
if SellerReview.objects.count() < 10:
    from apps.accounts.models import SellerReview
    sample_comments = [
        ("Fast Hetauda delivery!", 5,5,5),
        ("Authentic product, great seller communication.",5,4,5),
        ("Size exchange handled at doorstep in 2hrs — wow.",5,5,4),
        ("Good quality, a bit slow shipping Ward 10.",4,3,5),
        ("Trusted seller — 3rd order.",5,5,5),
    ]
    for vendor in VendorProfile.objects.filter(is_verified=True)[:4]:
        for i,(comment, comm, ship, acc) in enumerate(random.sample(sample_comments, 3)):
            SellerReview.objects.get_or_create(
                vendor=vendor,
                reviewer=customer,
                order=None,
                defaults=dict(
                    communication_rating=comm,
                    shipping_speed_rating=ship,
                    product_accuracy_rating=acc,
                    overall_rating=round((comm+ship+acc)/3),
                    title="Verified Hetauda buyer",
                    comment=comment,
                    would_recommend=True,
                    is_verified_purchase=True,
                )
            )
    print("✓ Seller reviews seeded")

print("\n" + "="*70)
print("✅ Makwanpur Mart seed complete!")
print(f"Categories: {Category.objects.count()}")
print(f"Vendors: {VendorProfile.objects.count()}  (verified: {VendorProfile.objects.filter(verification_status='verified').count()})")
print(f"Products live (approved): {Product.objects.filter(is_active=True, moderation_status='approved').count()}")
print(f"Users: {User.objects.count()}")
print("\nLogin accounts:")
print("  Admin / seller / customer — create via createsuperuser, or:")
print("  customer: sita.shrestha@makwanpur.test / customer123")
print("  vendors : *@makwanpur.test / vendor12345")
print("\nNext: python manage.py runserver")
