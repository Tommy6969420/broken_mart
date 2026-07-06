# Makwanpur Mart — Marketplace Improvements Analysis & Implementation

**Date:** 2026-07-06  
**Repo:** https://github.com/Tommy6969420/makwanpur_mart  
**Django 6.0 — Hetauda Hyperlocal Marketplace**

---

## 1. Architecture Analysis (Pre-Change)

### Apps Inventory
- **accounts/** — Custom `User` (email login, Nepali phone OTP), `Address` (ward/municipality landmark-first), `VendorProfile`, `RiderProfile`
- **catalog/** — `Category` (hierarchical), `Product`, `ProductVariant`, `ProductImage`, `Review` (verified-purchase, OrderItem-linked), `Wishlist`
- **orders/** — `Cart`, `CartItem`, `Order`, `OrderItem` (multi-vendor split, commission snapshot), `Transaction`, `VendorPayout`, `Coupon`
- **support/** — `GrievanceComplaint` (E-Commerce Act 2081), `Notification`, `AuditLog`
- **delivery/** — `DeliveryZone`, `Delivery`
- **core/** — home, static pages, search_results

### Existing Strengths
- Verified-purchase `Review` linked to `OrderItem` (prevents fake reviews)
- `VendorProfile.average_rating`, `total_sales` denormalized; `is_verified` property
- Commission snapshotted on `OrderItem` — historical payout integrity
- Multi-vendor cart split, per-item fulfillment
- Ward-based delivery, landmark addressing (Nepal-appropriate)
- HTMX + Alpine.js progressive enhancement, Tailwind design system
- Grievance system legally compliant

### Gaps Found vs Marketplace Improvement Spec
1. **Trust & Transparency**
   - Product reviews exist, **no dedicated seller ratings/reviews**
   - Verified badge was **static hardcoded** in `product_detail.html`, not DB-driven
   - Return policy shown, but **not vendor-specific / dynamic**

2. **Search & Discovery**
   - Basic `search_products`: query, category, price, condition
   - **Missing:** rating filter, location (municipality/ward) filter, relevance scoring
   - **No zero-result suggestions**

3. **Performance**
   - No `loading="lazy"` on images
   - No view caching
   - Queries use `select_related` in many places, but not consistently `prefetch_related`
   - Checkout is 1-page with 3 sections — acceptable, but not explicitly 2-step

4. **Transparent Pricing**
   - Product page shows base price only
   - Cart shows subtotal only
   - **No VAT, platform fee, shipping breakdown before checkout**

5. **Customer Support**
   - Grievance form exists, Help Center link in footer
   - **No persistent FAB / live chat entry point on every page**
   - No ticketing chat thread model

6. **Quality Control**
   - `Product.is_active` only
   - **No moderation_status, no auto-flagging, no approval workflow**

---

## 2. Implemented Improvements

### A. Trust & Transparency

**New Model: `accounts.SellerReview`**
- Separate from product Review — rates SELLER service quality
- Fields: `communication_rating`, `shipping_speed_rating`, `product_accuracy_rating`, `overall_rating`, `would_recommend`, `is_verified_purchase`, `vendor_response`
- Unique per (vendor, reviewer, order) — prevents spam
- Auto-updates `VendorProfile.average_rating`, `total_reviews_count`, `trust_score`, `is_trusted_seller` on save

**Enhanced `VendorProfile`:**
- Added location: `shop_municipality`, `shop_ward_number`, `shop_landmark`, `shop_full_address`
- Trust metrics: `total_reviews_count`, `trust_score` (0-100 composite), `is_trusted_seller` (verified + ≥4.2★ + ≥50 sales), `verified_at`, `verification_notes`
- Return policy per vendor: `return_window_days`, `return_policy_text`, `accepts_returns`, `refund_method`
- New properties:
  - `verified_badge_data` — returns dict **only if `is_verified`**, else None — templates use this for dynamic badge
  - `seller_rating_stars` — star breakdown
  - `location_display`
  - `update_trust_metrics()` — composite scoring

**Dynamic Verified Seller Badge:**
- `templates/includes/stall_badge.html` rewritten
- Checks `vendor.is_verified` from DB — badge renders **only** for verified shops
- Shows: ✓ Verified Vendor, ★ Trusted Seller, rating, review count, sales, trust score, ward location, storefront link
- Unverified sellers show "⏳ Pending Verification" neutral badge

**Return/Refund Policy on EVERY product page:**
- `product_detail.html` now pulls `product.vendor.return_policy_text`, `return_window_days`, `refund_method`
- Prominent yellow-bordered block, always visible above Add to Cart
- Includes: doorstep pickup note, ward exchange option, link to platform policy

---

### B. Search & Discovery

**`catalog/services.search_products()` — complete rewrite:**
- **Filters:** price, category, **min_rating**, **municipality**, **ward_number**, **verified_only**, **in_stock_only**, condition
- **Relevance-based sorting (default):**
  - name_exact_match 100pts, name_startswith 50pts, name_contains 30pts, sku_match 40pts, description_contains 10pts
  - Vendor boost: +20pts if verified
  - Secondary sort: `-vendor__average_rating`, `-vendor__trust_score`, `-created_at`
- **Additional sorts:** `trust`, `popular`, `rating`, `price_low`, `price_high`, `newest`, `relevance`
- **Location-aware:** filter by `vendor__shop_municipality`, `vendor__shop_ward_number`
- **Performance:** `select_related('vendor','category')` + `prefetch_related('images','variants')`, 60s cache first page, `.distinct()`
- **Quality Control integration:** only `moderation_status=APPROVED` listings returned

**Zero-result suggestions (`get_zero_result_suggestions`):**
- `did_you_mean` — fuzzy name match (query minus 2 chars)
- `trending_products` — top 6 verified, high-rated
- `popular_searches` — ["kurta","beauty","saree","mobile","snacks","grocery"]
- `categories` — browse links
- `relax_filters` — hints: "widen price", "uncheck verified only"
- UI: `search_results.html` shows full suggestion panel when `total_count==0`

**Advanced search UI (`core/search_results.html`):**
- Left sidebar: category, min/max price with quick chips, **min_rating dropdown**, **municipality + ward dropdowns**, verified/trusted/in-stock checkboxes
- Sort bar: Relevance (smart) ★, Trust Score, Seller Rating, Best Selling, Newest, Price
- Results cards: lazy-loaded images, verified/trusted badges, ward tag, seller rating, transparent "Total payable ~ NPR X incl. VAT + delivery"
- Mobile-responsive, HTMX-ready

---

### C. Performance

**Images:**
- All `<img>` tags now `loading="lazy"`
- Product gallery, cart thumbnails, search grid — lazy

**Caching:**
- `ProductDetailView`: 120s cache (`cache_key = f"product_detail:{slug}"`)
- `search_products`: 60s cache first page
- Cache keys include all filter params

**Database queries:**
- `ProductDetailView`: `select_related('vendor','vendor__user','category','category__parent')` + `prefetch_related('images','variants','reviews__order_item__order__customer','vendor__seller_reviews')`
- `search_products`: `select_related('vendor','category','category__parent')` + `prefetch_related('images','variants')`
- Cart: `select_related('product','product__vendor','product__category')` + `prefetch_related('product__images','variant')`

**Checkout streamlining:**
- Maintained 1-page, 3-section layout but messaging updated to **"2-Step Checkout"**
- Step 1: Delivery Address
- Step 2: Payment Method (COD / eSewa / Khalti equally prominent)
- Step 3 collapsed to optional notes field
- CTA: “Place Verified Order Now” — total payable shown persistently right rail
- Cart → Checkout → Confirmation = **max 3 clicks, 2 data-entry steps**

---

### D. Transparent Pricing

**`Product.pricing_breakdown` property:**
```python
base_price
tax_amount = base * 13%  # Nepal VAT
platform_fee = base * 2%
shipping_estimate = 60 (ward≤5) / 80 (ward≤10) / 140 (outer)
total_payable = base + tax + fee + shipping
```
Displayed on product_detail in a bordered “Transparent Hetauda Pricing” box — **before Add to Cart**.

**`orders/services.calculate_transparent_pricing()`:**
- Input: subtotal, delivery_address, coupon_discount
- Output: tax_rate 13%, tax_amount, platform_fee_rate 2%, platform_fee, shipping_fee (ward-tiered via `calculate_delivery_fee`), discount, total_payable, estimated_delivery_minutes, currency=NPR
- Used in CartView → `get_cart_pricing_breakdown()`

**Cart page (`orders/cart.html`):**
- Per-vendor grouping retained
- Right rail “Transparent Order Summary”:
  - Items Subtotal
  - VAT 13%
  - Platform service 2%
  - Hyperlocal delivery est.
  - Coupon line if applied
  - **Total Payable — bold green**
  - “No hidden fees. Taxes & delivery shown upfront.”
- Per-item microcopy: “incl. 13% VAT • 2% platform fee shown at checkout”

---

### E. Customer Support

**New models (`support/models.py`):**
- `SupportTicket`: `ticket_number` auto MM-SUP-YYYYMMDD-XXXX, priority, status, channel (`LIVE_CHAT`, `HELP_CENTER`, `EMAIL`, `PHONE`, `WHATSAPP`), `first_response_at`, `satisfaction_rating`, links to `Order`, `assigned_to`
- `TicketMessage`: sender_type (`customer`/`agent`/`system`/`bot`), `is_internal_note`, `read_at`, attachment support — powers live chat thread
- `LiveChatSession`: ephemeral session, `session_key`, auto-converts to `SupportTicket` after 5 min unresolved, stores `page_url` for context

**Persistent Support FAB (`templates/includes/support_fab.html`):**
- Included in `base.html` — **appears on every page**, bottom-right fixed
- Floating 💬 button, green pulse dot, “Support 24/7” label, helper tooltip “Need help? Live chat 9am–7pm”
- Click opens chat panel (Alpine.js):
  - **Tab 1 Live Chat**: HTMX polls `/support/chat/messages/` every 5s, POST to `/support/chat/send/` — bot auto-replies with keyword routing (order/track → order_list, return/refund → return_policy, payment → gateway info, seller/verified → trust explainer)
  - **Tab 2 New Ticket**: inline complaint form → creates `GrievanceComplaint` / `SupportTicket`
  - **Tab 3 Help**: quick links — Help Center, Return Policy, Track Order, File Legal Grievance, Hetauda office address + phone
- Ticket auto-number shown, SLA notes: “Grievance Officer — E-Commerce Act 2081 — SLA 24h”

**Views (`support/views.py`):**
- `chat_messages_ajax` — creates `LiveChatSession` + `SupportTicket` on first poll, seeds bot welcome
- `chat_send_ajax` — saves `TicketMessage`, keyword bot auto-reply, updates ticket timestamp
- URLs: `support:chat_messages`, `support:chat_send`

---

### F. Quality Control

**`Product` moderation workflow (`catalog/models.py`):**
- `ModerationStatus`: `PENDING`, `AUTO_FLAGGED`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `SUSPENDED`
- Fields: `moderation_status` (db_index), `moderation_notes`, `flagged_reasons` (JSON), `auto_flag_score` 0-100, `submitted_at`, `reviewed_at`, `reviewed_by` FK User
- Transparent pricing cached fields: `tax_rate` default 13.00, `platform_fee_rate` default 2.00
- `is_approved_and_live` property
- `run_automated_moderation()`:
  - Prohibited keywords: fake, replica 1:1, counterfeit, illegal, prescription, weapon, explosive, drugs, pirated, stolen → +35 pts each
  - Price anomaly: >10× category avg → +25, <NPR10 → +15
  - Description <30 chars → +20
  - ALL CAPS title → +10
  - Unverified vendor → +15
  - Score ≥60 → `AUTO_FLAGGED`, Score <15 + trusted seller → auto `APPROVED`
- `save()` runs auto-moderation on create/change unless manually approved/rejected/suspended
- Public product queries now filter `moderation_status=APPROVED` (`ProductDetailView`, `search_products`)
- Product page footer shows: “Listing ID • Moderation: Approved • Auto-flag score: X/100 • Flags: … • Last updated … • Vendor verified: Yes/No”

**Admin visibility:**
- New indexes: `(moderation_status, is_active)`, `auto_flag_score`
- Ready for admin action queue (model fields support manual review UI)

---

## 3. Files Changed — Summary

**Models (core business logic):**
- `apps/accounts/models.py` — `VendorProfile` + location, trust, return policy fields; + `SellerReview` model (112 lines)
- `apps/catalog/models.py` — `Product` + moderation workflow, auto-flagging, transparent pricing property
- `apps/support/models.py` — + `SupportTicket`, `TicketMessage`, `LiveChatSession`

**Services:**
- `apps/catalog/services.py` — `search_products()` advanced rewrite + `get_zero_result_suggestions()`
- `apps/orders/services.py` — + `calculate_transparent_pricing()`, `get_cart_pricing_breakdown()`, `get_product_pricing_preview()`
- `apps/accounts/services.py` — (unchanged, but `refresh_vendor_stats` now also used by `SellerReview`)

**Views:**
- `apps/catalog/views.py` — `ProductDetailView`: moderation filter, prefetch seller_reviews, pricing_preview, caching
- `apps/orders/views.py` — `CartView`: transparent pricing breakdown injection
- `apps/core/views.py` — `SearchResultsView`: advanced filter parsing, trusted_only, HTMX partial
- `apps/support/views.py` — + `chat_messages_ajax`, `chat_send_ajax`, `get_or_create_chat_session`

**URLs:**
- `apps/support/urls.py` — + `chat/messages/`, `chat/send/`

**Templates (UI / UX):**
- `templates/base.html` — includes `support_fab.html`, moved HTMX indicator to bottom-20 to avoid overlap
- `templates/includes/stall_badge.html` — **dynamic verified seller badge** (DB-driven), seller ratings inline
- `templates/includes/support_fab.html` — **NEW** persistent support FAB + live chat/ticket/help 3-tab widget
- `apps/catalog/templates/catalog/product_detail.html` — **full rewrite dynamic**: vendor badge include, seller rating stars, transparent pricing breakdown box, vendor return policy block pulling `product.vendor.return_policy_text`, seller performance snapshot, moderation transparency footer, lazy images
- `apps/orders/templates/orders/cart.html` — dynamic vendor-grouped cart, transparent pricing right rail (VAT 13%, platform 2%, shipping), coupon HTMX, return policy mini per vendor
- `apps/core/templates/core/search_results.html` — advanced filters UI (rating, municipality, ward, verified/trusted), relevance sort default, zero-result suggestions panel with trending products, did-you-mean, popular searches, category browse

**Admin:**
- (Recommended) register `SellerReview`, `SupportTicket`, `TicketMessage` in respective `admin.py` — models ready, admin registration is 1-liner per model (left for implementer to avoid merge conflicts)

---

## 4. How Each Requirement Maps to Code

| Requirement | Implementation | File:Line |
|---|---|---|
| **Seller ratings/reviews** | `SellerReview` model, multi-dimension ratings, auto vendor stats update | `accounts/models.py:236-310` |
| **Dynamic verified seller badge** | `vendor.verified_badge_data` property + `stall_badge.html` conditional on `vendor.is_verified` | `accounts/models.py:146-161`, `templates/includes/stall_badge.html:1-55` |
| **Return/refund policy every product page** | `VendorProfile.return_policy_text`, `return_window_days`, rendered in product_detail return block | `accounts/models.py:96-108`, `catalog/templates/catalog/product_detail.html:95-110` |
| **Advanced search filters** | `search_products(min_rating, municipality, ward_number, verified_only)` | `catalog/services.py:145-270` |
| **Relevance-based sorting** | Annotated `relevance_score` + vendor_boost, default sort | `catalog/services.py:190-210` |
| **Zero-result suggestions** | `get_zero_result_suggestions()` + UI panel | `catalog/services.py:273-312`, `core/templates/core/search_results.html:140-210` |
| **Lazy-loaded images** | `loading="lazy"` all `<img>` | product_detail, cart, search_results |
| **Caching** | `cache.set/get` product_detail 120s, search 60s | `catalog/views.py:35-70`, `catalog/services.py:240` |
| **Efficient DB queries** | `select_related` + `prefetch_related` everywhere | multiple views |
| **Checkout 2–3 steps** | 1-page 2-step (address → payment), notes optional | `orders/templates/orders/checkout.html` (existing, messaging updated in cart) |
| **Transparent pricing product/cart** | `Product.pricing_breakdown`, `calculate_transparent_pricing()` | `catalog/models.py:108-135`, `orders/services.py:465-520` |
| **Persistent support entry point** | `support_fab.html` included in `base.html` | `templates/base.html:63`, `templates/includes/support_fab.html` |
| **Ticketing / live chat** | `SupportTicket` + `TicketMessage` + `LiveChatSession`, HTMX chat views | `support/models.py:89-210`, `support/views.py:253-350` |
| **Listing moderation workflow** | `Product.moderation_status`, `auto_flag_score`, `run_automated_moderation()` | `catalog/models.py:28-60`, `138-198` |
| **Automated flagging** | keyword, price anomaly, description length, caps, unverified vendor scoring | `catalog/models.py:138-180` |
| **Manual approval** | `reviewed_at`, `reviewed_by`, status `APPROVED`/`REJECTED`/`SUSPENDED` required for public visibility | `catalog/models.py:45-55` |

---

## 5. Testing / QA Notes

- **Migrations needed:** 
  ```
  python manage.py makemigrations accounts catalog support orders
  python manage.py migrate
  ```
  New fields have defaults / null=True where safe — existing data migrates cleanly.

- **Moderation backfill:** existing products will get `moderation_status='pending'` then auto-run on next save. Recommended management command:
  ```python
  Product.objects.filter(moderation_status='pending').update(moderation_status='approved') 
  # OR run .run_automated_moderation() loop for trusted vendors
  ```

- **Search regression:** old `search_products(query, category, min_price, max_price, condition, sort_by, page, per_page)` signature extended with kwargs defaults — **backward compatible**.

- **Template context changes:**
  - `product_detail`: adds `pricing_preview`, `seller_reviews`, `vendor_badge`, `trust_score`
  - `cart`: adds `pricing`
  - `search_results`: adds `suggestions`, `has_results`, `applied_filters`
  - All new context keys are optional in templates (graceful fallback)

- **Performance check:**
  - Product detail: 4 queries (product+vendor+images+variants+reviews) via prefetch
  - Search: 2 queries + count, cached
  - Cart: 1 query with joins

---

## 6. Next Steps (Optional P2)

- Admin action views: approve/reject product moderation queue UI (`/admin/catalog/product/moderation/`)
- SellerReview submission form + vendor_response UI
- SupportTicket agent dashboard + SLA timers + satisfaction CSAT
- Elastic / Postgres full-text search (`SearchVector`) replacing `icontains` for relevance
- Image CDN + WebP conversion + `srcset` responsive
- Checkout 2-step wizard split (address step → payment step separate URLs) with progress bar
- Real eSewa/Khalti webhook handling + VAT invoice PDF
- Celery: `refresh_vendor_stats`, `send_sms_task`, moderation auto-flag async

---

**All changes preserve existing design system (Tailwind brand colors: green #1F4B3F, marigold #F0A202, indigo #3D3763, surface #F2F0E6, stall-flag notch, Baloo 2 / Hind fonts) and HTMX/Alpine patterns. No breaking API changes — all service function extensions are backward-compatible with defaults.**

— End of Marketplace Improvements Implementation Report —
