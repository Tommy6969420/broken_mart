"""
Services for catalog app.
Business logic for products, categories, reviews, wishlist, and search.
"""
from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone

from .models import Category, Product, ProductImage, ProductVariant, Review, Wishlist


# =============================================================================
# Product Services
# =============================================================================

def get_active_products():
    """Get all active products."""
    return Product.objects.filter(is_active=True)


def get_product_by_slug(slug: str) -> Product:
    """Get product by slug."""
    return Product.objects.get(slug=slug, is_active=True)


def get_products_by_category(category: Category, include_subcategories: bool = True) -> list:
    """
    Get products in a category.
    If include_subcategories is True, also include products from child categories.
    """
    if include_subcategories:
        category_ids = [category.id]
        for child in category.children.all():
            category_ids.append(child.id)
            # Get grandchildren
            category_ids.extend(child.children.values_list('id', flat=True))
        
        return Product.objects.filter(
            category_id__in=category_ids,
            is_active=True
        ).select_related('vendor', 'category')
    
    return Product.objects.filter(
        category=category,
        is_active=True
    ).select_related('vendor', 'category')


def get_product_with_details(product_id: int) -> dict:
    """Get comprehensive product details."""
    product = Product.objects.select_related(
        'vendor', 'vendor__user', 'category', 'category__parent'
    ).prefetch_related('images', 'variants', 'reviews').get(id=product_id, is_active=True)
    
    # Get review stats
    review_stats = Review.objects.filter(product=product).aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id')
    )
    
    # Calculate total stock (considering variants)
    if product.has_variants:
        total_stock = product.variants.aggregate(total=Sum('stock_quantity'))['total'] or 0
    else:
        total_stock = product.stock_quantity
    
    return {
        'product': product,
        'review_stats': review_stats,
        'total_stock': total_stock,
        'is_available': total_stock > 0,
    }


def available_stock(product: Product, variant: ProductVariant = None) -> int:
    """
    Get available stock for a product (optionally specific variant).
    """
    if variant:
        return variant.stock_quantity
    
    if product.has_variants:
        return product.variants.aggregate(total=Sum('stock_quantity'))['total'] or 0
    
    return product.stock_quantity


def check_product_available(product: Product, quantity: int = 1, variant: ProductVariant = None) -> bool:
    """Check if requested quantity is available."""
    return available_stock(product, variant) >= quantity


# =============================================================================
# Category Services
# =============================================================================

def get_categories_hierarchy():
    """Get category hierarchy for navigation."""
    return Category.objects.filter(
        is_active=True,
        parent__isnull=True
    ).prefetch_related('children', 'children__children')


def get_category_breadcrumb(category: Category) -> list:
    """Get breadcrumb path for a category."""
    path = []
    current = category
    while current:
        path.insert(0, current)
        current = current.parent
    return path


def get_category_product_count(category: Category, include_subcategories: bool = True) -> int:
    """Get total product count for a category."""
    if include_subcategories:
        category_ids = [category.id]
        for child in category.children.all():
            category_ids.append(child.id)
            category_ids.extend(child.children.values_list('id', flat=True))
        
        return Product.objects.filter(category_id__in=category_ids, is_active=True).count()
    
    return Product.objects.filter(category=category, is_active=True).count()


# =============================================================================
# Search Services
# =============================================================================

def search_products(query: str, category: Category = None, 
                    min_price: float = None, max_price: float = None,
                    condition: str = None, sort_by: str = 'relevance',
                    page: int = 1, per_page: int = 12,
                    # --- Marketplace Improvement: advanced filters ---
                    min_rating: float = None,
                    municipality: str = None,
                    ward_number: int = None,
                    verified_only: bool = False,
                    in_stock_only: bool = True) -> dict:
    """
    Advanced search with filters (price, category, rating, location),
    relevance-based sorting, and zero-result suggestions.
    
    Marketplace Improvement: Search & Discovery
    """
    from django.db.models import Case, When, Value, IntegerField, F
    from django.core.cache import cache
    
    # Performance: cache frequent empty queries for 60s
    cache_key = f"search:{query}:{category.id if category else 'all'}:{min_price}:{max_price}:{min_rating}:{municipality}:{ward_number}:{verified_only}:{sort_by}:{page}"
    cached = cache.get(cache_key)
    if cached and page == 1:  # only cache first page
        # still return fresh zero-result suggestions check
        pass  # continue to compute to ensure freshness - cache disabled for now in dev

    # Base queryset — Quality Control: only APPROVED listings
    products = Product.objects.filter(
        is_active=True,
        moderation_status=Product.ModerationStatus.APPROVED
    ).select_related(
        'vendor', 'category', 'category__parent'
    ).prefetch_related('images', 'variants')

    # Text search with relevance scoring
    relevance_score = Value(0, output_field=IntegerField())
    if query and len(query.strip()) >= 2:
        q = query.strip()
        # Build relevance annotations
        products = products.annotate(
            name_exact_match=Case(
                When(name__iexact=q, then=Value(100)),
                default=Value(0),
                output_field=IntegerField()
            ),
            name_startswith=Case(
                When(name__istartswith=q, then=Value(50)),
                default=Value(0),
                output_field=IntegerField()
            ),
            name_contains=Case(
                When(name__icontains=q, then=Value(30)),
                default=Value(0),
                output_field=IntegerField()
            ),
            description_contains=Case(
                When(description__icontains=q, then=Value(10)),
                default=Value(0),
                output_field=IntegerField()
            ),
            sku_match=Case(
                When(sku__icontains=q, then=Value(40)),
                default=Value(0),
                output_field=IntegerField()
            ),
        ).annotate(
            relevance_score=F('name_exact_match') + F('name_startswith') + 
                           F('name_contains') + F('description_contains') + F('sku_match')
        )
        # Filter to relevant results
        products = products.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(sku__icontains=q) |
            Q(category__name__icontains=q) |
            Q(vendor__shop_name__icontains=q)
        )
    else:
        products = products.annotate(relevance_score=Value(0, output_field=IntegerField()))
    
    # Category filter
    if category:
        category_ids = [category.id]
        for child in category.children.all():
            category_ids.append(child.id)
            # grandchildren
            category_ids.extend(list(child.children.values_list('id', flat=True)))
        products = products.filter(category_id__in=category_ids)
    
    # Price filters — improved to handle discounted_price correctly
    if min_price is not None:
        products = products.filter(
            Q(discounted_price__isnull=False, discounted_price__gte=min_price) |
            Q(discounted_price__isnull=True, price__gte=min_price)
        )
    if max_price is not None:
        products = products.filter(
            Q(discounted_price__isnull=False, discounted_price__lte=max_price) |
            Q(discounted_price__isnull=True, price__lte=max_price)
        )
    
    # Condition filter
    if condition:
        products = products.filter(condition=condition)
    
    # --- NEW: Rating filter ---
    if min_rating is not None:
        try:
            min_rating = float(min_rating)
            products = products.filter(vendor__average_rating__gte=min_rating)
        except (ValueError, TypeError):
            pass

    # --- NEW: Location filter (municipality / ward) ---
    if municipality:
        products = products.filter(vendor__shop_municipality=municipality)
    if ward_number:
        try:
            products = products.filter(vendor__shop_ward_number=int(ward_number))
        except (ValueError, TypeError):
            pass

    # --- NEW: Verified seller only ---
    if verified_only:
        products = products.filter(vendor__verification_status='verified')

    # --- NEW: In-stock only ---
    if in_stock_only:
        products = products.filter(
            Q(variants__stock_quantity__gt=0) | 
            Q(stock_quantity__gt=0, variants__isnull=True)
        ).distinct()

    # Sorting — relevance-based is default
    if sort_by == 'relevance' and query:
        # Boost: verified vendors + high rating + trust score
        products = products.annotate(
            vendor_boost=Case(
                When(vendor__verification_status='verified', then=Value(20)),
                default=Value(0),
                output_field=IntegerField()
            )
        ).order_by('-relevance_score', '-vendor_boost', '-vendor__average_rating', '-vendor__trust_score', '-created_at')
    else:
        sort_options = {
            'newest': '-created_at',
            'price_low': 'price',
            'price_high': '-price',
            'rating': '-vendor__average_rating',
            'popular': '-vendor__total_sales',
            'trust': '-vendor__trust_score',
            'relevance': '-relevance_score',
        }
        order_field = sort_options.get(sort_by, '-created_at')
        # For price_low/high prefer discounted_price
        if sort_by == 'price_low':
            products = products.order_by(F('discounted_price').asc(nulls_last=True), 'price')
        elif sort_by == 'price_high':
            products = products.order_by(F('discounted_price').desc(nulls_last=True), '-price')
        else:
            products = products.order_by(order_field, '-created_at')

    # Pagination with efficient count
    total_count = products.distinct().count()
    start = (page - 1) * per_page
    end = start + per_page
    results = list(products.distinct()[start:end])

    # --- Zero-result helpful suggestions ---
    suggestions = {}
    if total_count == 0:
        suggestions = get_zero_result_suggestions(query, category, min_price, max_price)

    # Cache first page 60s for performance
    output = {
        'results': results,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page if total_count else 1,
        'suggestions': suggestions,
        'has_results': total_count > 0,
        'query': query,
        'applied_filters': {
            'category': category.slug if category else None,
            'min_price': min_price,
            'max_price': max_price,
            'min_rating': min_rating,
            'municipality': municipality,
            'ward_number': ward_number,
            'verified_only': verified_only,
        }
    }

    if page == 1 and total_count > 0:
        try:
            cache.set(cache_key, output, 60)
        except Exception:
            pass

    return output


def get_zero_result_suggestions(query: str, category=None, min_price=None, max_price=None):
    """Helpful suggestions for zero-result searches — Search & Discovery improvement."""
    suggestions = {
        "message": "No exact matches found in Hetauda Bazaar — try these:",
        "popular_searches": [],
        "trending_products": [],
        "relax_filters": [],
        "did_you_mean": [],
        "categories": [],
    }
    # Popular searches (hardcoded + dynamic)
    popular_terms = ["kurta", "beauty", "saree", "mobile", "snacks", "grocery"]
    if query:
        # did-you-mean style: strip last char, suggest close matches
        from django.db.models import Q
        similar = Product.objects.filter(
            name__icontains=query[:max(2, len(query)-2)],
            is_active=True,
            moderation_status=Product.ModerationStatus.APPROVED
        ).values_list('name', flat=True).distinct()[:5]
        suggestions["did_you_mean"] = list(similar)
        # filter relaxation hints
        if min_price or max_price:
            suggestions["relax_filters"].append("Try widening your price range")
        if category:
            suggestions["relax_filters"].append(f"Browse all in {category.parent.name if category.parent else 'all categories'}")
        suggestions["relax_filters"].append("Search verified sellers only — uncheck to see more")
    # trending products
    try:
        trending = Product.objects.filter(
            is_active=True,
            moderation_status=Product.ModerationStatus.APPROVED,
            vendor__verification_status='verified'
        ).select_related('vendor').order_by('-vendor__average_rating', '-created_at')[:6]
        suggestions["trending_products"] = [
            {"name": p.name, "slug": p.slug, "price": float(p.effective_price), "vendor": p.vendor.shop_name}
            for p in trending
        ]
    except Exception:
        pass
    # categories
    cats = Category.objects.filter(is_active=True, parent__isnull=True)[:6]
    suggestions["categories"] = [{"name": c.name, "slug": c.slug} for c in cats]
    suggestions["popular_searches"] = popular_terms[:6]
    return suggestions


# =============================================================================
# Wishlist Services
# =============================================================================

def add_to_wishlist(user, product: Product) -> Wishlist:
    """Add product to user's wishlist."""
    wishlist_item, created = Wishlist.objects.get_or_create(
        user=user,
        product=product
    )
    return wishlist_item, created


def remove_from_wishlist(user, product: Product) -> bool:
    """Remove product from user's wishlist."""
    deleted, _ = Wishlist.objects.filter(user=user, product=product).delete()
    return deleted > 0


def toggle_wishlist(user, product: Product) -> bool:
    """
    Toggle wishlist status.
    Returns True if added, False if removed.
    """
    try:
        item = Wishlist.objects.get(user=user, product=product)
        item.delete()
        return False  # Removed
    except Wishlist.DoesNotExist:
        Wishlist.objects.create(user=user, product=product)
        return True  # Added


def get_user_wishlist(user) -> list:
    """Get user's wishlist items with product details."""
    return Wishlist.objects.filter(user=user).select_related(
        'product', 'product__vendor', 'product__category', 'product__images'
    ).order_by('-added_at')


def is_in_wishlist(user, product: Product) -> bool:
    """Check if product is in user's wishlist."""
    return Wishlist.objects.filter(user=user, product=product).exists()


# =============================================================================
# Review Services
# =============================================================================

def submit_review(user, product: Product, order_item, rating: int, comment: str = '') -> Review:
    """Submit a product review."""
    review = Review.objects.create(
        product=product,
        order_item=order_item,
        rating=rating,
        comment=comment
    )
    
    # Update vendor stats asynchronously (in production, use Celery)
    from apps.accounts.services import refresh_vendor_stats
    refresh_vendor_stats(product.vendor)
    
    return review


def get_product_reviews(product: Product, page: int = 1, per_page: int = 10) -> dict:
    """Get paginated reviews for a product."""
    reviews = Review.objects.filter(product=product).select_related(
        'order_item', 'order_item__order', 'order_item__order__customer'
    ).order_by('-created_at')
    
    total_count = reviews.count()
    start = (page - 1) * per_page
    end = start + per_page
    
    return {
        'reviews': list(reviews[start:end]),
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page,
    }


def get_review_stats(product: Product) -> dict:
    """Get review statistics for a product."""
    stats = Review.objects.filter(product=product).aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id'),
        rating_1=Count('id', filter=Q(rating=1)),
        rating_2=Count('id', filter=Q(rating=2)),
        rating_3=Count('id', filter=Q(rating=3)),
        rating_4=Count('id', filter=Q(rating=4)),
        rating_5=Count('id', filter=Q(rating=5)),
    )
    
    return stats


def vendor_respond_to_review(review: Review, response: str) -> Review:
    """Add vendor response to a review."""
    review.vendor_response = response
    review.save(update_fields=['vendor_response'])
    return review


# =============================================================================
# Vendor Product Management
# =============================================================================

def get_vendor_products(vendor, include_inactive: bool = False) -> list:
    """Get all products for a vendor."""
    queryset = Product.objects.filter(vendor=vendor)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset.select_related('category').prefetch_related('images', 'variants').order_by('-created_at')


def create_product(vendor, data: dict) -> Product:
    """Create a new product for a vendor."""
    from django.db.models import F
    
    category = data.get('category')
    
    product = Product.objects.create(
        vendor=vendor,
        name=data['name'],
        category=category,
        description=data.get('description', ''),
        price=data['price'],
        discounted_price=data.get('discounted_price'),
        stock_quantity=data.get('stock_quantity', 0),
        sku=data.get('sku', ''),
        condition=data.get('condition', Product.Condition.NEW),
        is_active=data.get('is_active', True),
        slug=data.get('slug', f"{vendor.shop_slug}-{data['name'].lower().replace(' ', '-')}")
    )
    
    return product


def update_product_stock(product: Product, quantity_change: int, variant: ProductVariant = None) -> bool:
    """
    Update product stock (decrease for orders, increase for restocks).
    Returns True if successful.
    """
    if variant:
        variant.stock_quantity = max(0, variant.stock_quantity + quantity_change)
        variant.save(update_fields=['stock_quantity'])
    else:
        product.stock_quantity = max(0, product.stock_quantity + quantity_change)
        product.save(update_fields=['stock_quantity'])
    
    return True


# =============================================================================
# Featured Products
# =============================================================================

def get_featured_products(limit: int = 8) -> list:
    """Get featured products for homepage."""
    return Product.objects.filter(
        is_active=True,
        vendor__verification_status='verified'
    ).select_related('vendor', 'category').prefetch_related(
        'images'
    ).order_by('-vendor__average_rating', '-created_at')[:limit]


def get_new_arrivals(limit: int = 12) -> list:
    """Get newest products."""
    return Product.objects.filter(
        is_active=True
    ).select_related('vendor', 'category').prefetch_related(
        'images'
    ).order_by('-created_at')[:limit]


def get_best_sellers(limit: int = 8) -> list:
    """Get best selling products."""
    return Product.objects.filter(
        is_active=True,
        vendor__total_sales__gt=0
    ).select_related('vendor', 'category').prefetch_related(
        'images'
    ).order_by('-vendor__total_sales')[:limit]