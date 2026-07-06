#!/usr/bin/env python
"""
Makwanpur Mart — Production Seed Script
Run: python manage.py shell < seed.py
  or: python manage.py shell
      >>> exec(open('seed.py').read())
Creates: categories, vendors (verified), products (approved), users (customer, agent, riders),
addresses, delivery zones, sample orders & dispatch drops, support tickets, complaints, seller reviews, coupons.
All data is Hetauda / Makwanpur authentic, no dummy lorem ipsum.
"""
import os, sys, django, random
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils.text import slugify
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from apps.accounts.models import User, VendorProfile, Address, RiderProfile, SellerReview
from apps.catalog.models import Category, Product, ProductImage, ProductVariant, Review
from apps.orders.models import Coupon, Order, OrderItem, Transaction
from apps.delivery.models import DeliveryZone, Delivery
from apps.support.models import SupportTicket, TicketMessage, GrievanceComplaint
from django.contrib.auth import get_user_model

User = get_user_model()

print("🌱 Makwanpur Mart — Seeding Hetauda Bazaar (Makwanpur District, Nepal)")
print("="*70)

# Safe wipe check
wipe = os.environ.get('WIPE_DATA', 'no').lower() == 'yes'
try:
    if not wipe and sys.stdin.isatty():
        wipe = input("Wipe existing catalog & demo data? (yes/NO): ").lower() == 'yes'
except Exception:
    pass

if wipe:
    print("Wiping existing records...")
    TicketMessage.objects.all().delete()
    SupportTicket.objects.all().delete()
    GrievanceComplaint.objects.all().delete()
    Delivery.objects.all().delete()
    OrderItem.objects.all().delete()
    Order.objects.all().delete()
    Review.objects.all().delete()
    ProductImage.objects.all().delete()
    ProductVariant.objects.all().delete()
    Product.objects.all().delete()
    SellerReview.objects.all().delete()
    RiderProfile.objects.all().delete()
    VendorProfile.objects.all().delete()
    DeliveryZone.objects.all().delete()
    Category.objects.all().delete()
    User.objects.filter(role__in=['vendor', 'rider', 'admin']).delete()
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

# 2. Delivery Zones — Makwanpur District Hyperlocal
zones_data = [
    ("Hetauda Central Bazaar (Wards 1-5)", [1, 2, 3, 4, 5], Decimal("60.00"), 25),
    ("Hetauda Industrial & Suburban (Wards 6-11)", [6, 7, 8, 9, 10, 11], Decimal("80.00"), 35),
    ("Makwanpur Outer Wards (Wards 12-19)", [12, 13, 14, 15, 16, 17, 18, 19], Decimal("140.00"), 60),
]
zones_map = {}
for zname, wards, fee, mins in zones_data:
    dz, z_created = DeliveryZone.objects.get_or_create(
        name=zname,
        defaults=dict(ward_numbers=wards, base_delivery_fee=fee, estimated_delivery_time_minutes=mins, is_active=True)
    )
    zones_map[zname] = dz
    if z_created: print(f"  + Delivery Zone: {zname} (NPR {fee})")

# 3. Support Agent & Superuser Admin
agent_user, a_created = User.objects.get_or_create(
    email="agent@makwanpur.test",
    defaults=dict(
        username="support_agent",
        phone_number="+9779841000999",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=False,
        is_active=True,
        is_phone_verified=True,
        first_name="Pooja", last_name="Adhikari"
    )
)
if a_created:
    agent_user.set_password("agent12345")
    agent_user.save()
    print("✓ Support Desk Agent created: agent@makwanpur.test / agent12345")

# 4. Delivery Riders (KYC Verified vs Unverified)
rider1_user, r1_created = User.objects.get_or_create(
    email="bikash.thapa@makwanpur.test",
    defaults=dict(
        username="bikasthapa",
        phone_number="+9779845000111",
        role=User.Role.RIDER,
        is_active=True,
        is_phone_verified=True,
        first_name="Bikash", last_name="Thapa"
    )
)
if r1_created:
    rider1_user.set_password("rider12345")
    rider1_user.save()
rider1, _ = RiderProfile.objects.get_or_create(
    user=rider1_user,
    defaults=dict(
        vehicle_type=RiderProfile.VehicleType.BIKE,
        kyc_status=RiderProfile.KYCStatus.VERIFIED,
        is_available=True,
        current_zone=zones_map["Hetauda Central Bazaar (Wards 1-5)"],
        total_deliveries=142,
        citizenship_number="27-01-76-04211",
        license_number="01-06-889123",
        vehicle_registration_number="Ba 19 Pa 4812",
        permanent_address="Hetauda-4, Main Bazaar",
        current_municipality="Hetauda",
        current_ward=4,
        kyc_verified_at=timezone.now() - timedelta(days=45),
        kyc_verified_by=agent_user,
        average_delivery_rating=Decimal("4.85"),
        total_ratings=39
    )
)
print(f"✓ Verified Rider: bikash.thapa@makwanpur.test / rider12345 ({rider1.get_kyc_status_display()})")

rider2_user, r2_created = User.objects.get_or_create(
    email="ramesh.rai@makwanpur.test",
    defaults=dict(
        username="rameshrai",
        phone_number="+9779845000222",
        role=User.Role.RIDER,
        is_active=True,
        is_phone_verified=True,
        first_name="Ramesh", last_name="Rai"
    )
)
if r2_created:
    rider2_user.set_password("rider12345")
    rider2_user.save()
rider2, _ = RiderProfile.objects.get_or_create(
    user=rider2_user,
    defaults=dict(
        vehicle_type=RiderProfile.VehicleType.BICYCLE,
        kyc_status=RiderProfile.KYCStatus.PENDING,
        is_available=False,
        current_zone=zones_map["Hetauda Central Bazaar (Wards 1-5)"],
        total_deliveries=0,
        citizenship_number="27-01-78-99120",
        permanent_address="Hetauda-2, Bank Road",
        current_municipality="Hetauda",
        current_ward=2
    )
)
print(f"⏳ Unverified Rider: ramesh.rai@makwanpur.test / rider12345 ({rider2.get_kyc_status_display()})")

# 5. Vendors — verified Hetauda shops
vendors_data = [
    {
        "email": "shrestha_cloth@makwanpur.test",
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
    email = v["email"]
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
            trust_score=min(30 + int(float(v["rating"])*12) + v["sales"]//10 + min(v["reviews"],10), 100) if v["verified"] else 45,
            is_trusted_seller=v["verified"] and float(v["rating"]) >= 4.2 and v["sales"] >= 50,
            payout_method="esewa",
            payout_account_details="eSewa ID: 98XXXXXXXX (encrypted in prod)",
            return_window_days=3,
            return_policy_text="3-Day Doorstep Replacement: size/fit issues or manufacturing defects — rider pickup free within Hetauda wards 1-19. Exchange at Ward {} physical stall.".format(v["ward"]),
            accepts_returns=True,
            refund_method="both",
        )
    )
    vendors[v["shop_slug"]] = vendor
    print(f"{'✓' if v['verified'] else '⏳'} Vendor: {vendor.shop_name} — {vendor.average_rating}★ — Trust {vendor.trust_score}/100")

# 6. Products — approved, with transparent pricing
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
        if counter > 20: break
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
            auto_flag_score=random.randint(0, 12),
            flagged_reasons=[],
            reviewed_at=timezone.now(),
            tax_rate=Decimal("13.00"),
            platform_fee_rate=Decimal("2.00"),
        )
    )
    if created:
        for size, color, stock, price_override in p.get("variants", []):
            ProductVariant.objects.create(
                product=product,
                size=size,
                color=color,
                stock_quantity=stock,
                price_override=Decimal(str(price_override)) if price_override else None
            )
        created_products.append(product)
        print(f"  + {product.name} — NPR {product.effective_price}")

# 7. Demo Customer & Address (with exact Makwanpur GPS pin)
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
        latitude=Decimal("27.428700"),
        longitude=Decimal("85.032000"),
    )
)

# 8. Sample Orders & Unassigned Delivery Drop Task (For Rider Dispatch Feed)
sample_prod = created_products[0] if created_products else Product.objects.first()
if sample_prod and Order.objects.count() == 0:
    order = Order.objects.create(
        customer=customer,
        delivery_address=addr,
        status=Order.Status.CONFIRMED,
        subtotal=sample_prod.effective_price,
        delivery_fee=Decimal("60.00"),
        discount_amount=Decimal("0.00"),
        total_amount=sample_prod.effective_price + Decimal("60.00"),
        payment_method="cod",
        payment_status=Order.PaymentStatus.PENDING,
        special_instructions="Ring top floor bell upon arrival."
    )
    OrderItem.objects.create(
        order=order,
        product=sample_prod,
        vendor=sample_prod.vendor,
        quantity=1,
        unit_price=sample_prod.effective_price,
        commission_amount=sample_prod.effective_price * Decimal(str(sample_prod.vendor.commission_rate)) / Decimal("100"),
        item_status=OrderItem.ItemStatus.CONFIRMED
    )
    # Unassigned drop task in rider dispatch feed
    Delivery.objects.create(
        order=order,
        status=Delivery.Status.UNASSIGNED,
        delivery_fee_owed_to_rider=Decimal("48.00")
    )
    print(f"✓ Sample Order #{order.order_number} and Unassigned Delivery created in Ward 4 dispatch pool")

# 9. Support Tickets & Messages (For Support Agent Desk Console)
if SupportTicket.objects.count() == 0:
    ticket = SupportTicket.objects.create(
        user=customer,
        subject="Delivery time inquiry for Kurta Set order",
        category="delivery_issue",
        priority=SupportTicket.Priority.HIGH,
        status=SupportTicket.Status.WAITING_CUSTOMER,
        channel=SupportTicket.Channel.LIVE_CHAT,
        order=Order.objects.first(),
        assigned_to=agent_user,
        first_response_at=timezone.now() - timedelta(minutes=15)
    )
    TicketMessage.objects.create(
        ticket=ticket,
        sender=customer,
        sender_type=TicketMessage.SenderType.CUSTOMER,
        sender_name="Sita Shrestha",
        message="Namaste! I ordered the Traditional Kurta Set. Will your rider call before arriving at Pashupati Temple Gate?"
    )
    TicketMessage.objects.create(
        ticket=ticket,
        sender=agent_user,
        sender_type=TicketMessage.SenderType.AGENT,
        sender_name="Pooja Adhikari (Support Agent)",
        message="Namaste Sita ji! Yes, our Hetauda rider Bikash Thapa is assigned to Ward 4 and will call your number +9779845123456 ~10 minutes prior to delivery."
    )
    print(f"✓ Sample Support Ticket #{ticket.ticket_number} seeded for Agent Desk Console")

# 10. Formal Grievance Complaint (E-Commerce Act 2081)
if GrievanceComplaint.objects.count() == 0 and Order.objects.exists():
    GrievanceComplaint.objects.create(
        order=Order.objects.first(),
        raised_by=customer,
        category="product_issue",
        description="Requested size exchange for Kurta set. Need L instead of M.",
        status="in_review",
        resolution_notes="Mediator contacted Shrestha Cloth Store. Exchange approved at Ward 4 stall."
    )
    print("✓ Formal Grievance Complaint seeded for Legal Compliance Queue")

# 11. Coupons
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

# 12. Seller reviews (Trust & Transparency)
if SellerReview.objects.count() < 10:
    sample_comments = [
        ("Fast Hetauda delivery!", 5, 5, 5),
        ("Authentic product, great seller communication.", 5, 4, 5),
        ("Size exchange handled at doorstep in 2hrs — wow.", 5, 5, 4),
        ("Good quality, a bit slow shipping Ward 10.", 4, 3, 5),
        ("Trusted seller — 3rd order.", 5, 5, 5),
    ]
    for vendor in VendorProfile.objects.filter(verification_status='verified')[:4]:
        for i, (comment, comm, ship, acc) in enumerate(random.sample(sample_comments, 3)):
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
print(f"Delivery Zones: {DeliveryZone.objects.count()}")
print(f"Vendors: {VendorProfile.objects.count()}  (verified: {VendorProfile.objects.filter(verification_status='verified').count()})")
print(f"Products live: {Product.objects.filter(is_active=True, moderation_status='approved').count()}")
print(f"Users: {User.objects.count()} (Riders: {RiderProfile.objects.count()})")
print(f"Support Tickets: {SupportTicket.objects.count()} | Grievances: {GrievanceComplaint.objects.count()}")
print("\n🔑 Login Credentials:")
print("  Support Desk Agent : agent@makwanpur.test / agent12345")
print("  Customer           : sita.shrestha@makwanpur.test / customer123")
print("  Verified Rider     : bikash.thapa@makwanpur.test / rider12345")
print("  Unverified Rider   : ramesh.rai@makwanpur.test / rider12345")
print("  Vendors            : shrestha_cloth@makwanpur.test / vendor12345")
print("\nNext: python manage.py runserver")
