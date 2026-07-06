"""
Views for core app.
Handles homepage, about, contact, static pages, and search.
"""
from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView, View

from apps.catalog.models import Category, Product
from apps.catalog.services import get_featured_products, get_new_arrivals, search_products
from apps.support.services import get_faq_categories


# =============================================================================
# Homepage
# =============================================================================

class HomeView(TemplateView):
    """Homepage with featured products and categories."""
    
    template_name = 'core/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Featured products
        context['featured_products'] = get_featured_products(limit=8)
        
        # New arrivals
        context['new_arrivals'] = get_new_arrivals(limit=12)
        
        # Categories with product counts
        categories = Category.objects.filter(
            is_active=True,
            parent__isnull=True
        ).prefetch_related('children')[:8]
        
        for cat in categories:
            cat.product_count = cat.products.filter(is_active=True).count()
        
        context['categories'] = categories
        
        return context


# =============================================================================
# Static Pages
# =============================================================================

class AboutView(TemplateView):
    """About page."""
    template_name = 'core/about.html'


class ContactView(TemplateView):
    """Contact page with form."""
    template_name = 'core/contact.html'
    
    def post(self, request):
        name = request.POST.get('name', '')
        email = request.POST.get('email', '')
        subject = request.POST.get('subject', '')
        message_text = request.POST.get('message', '')
        
        if name and email and subject and message_text:
            # In production, would send email or create ticket
            messages.success(request, 'Thank you for your message! We will get back to you soon.')
        else:
            messages.error(request, 'Please fill in all fields.')
        
        return render(request, self.template_name)


class ReturnPolicyView(TemplateView):
    """Return policy page."""
    template_name = 'core/return_policy.html'


class PrivacyView(TemplateView):
    """Privacy policy page."""
    template_name = 'core/privacy.html'


class TermsView(TemplateView):
    """Terms of service page."""
    template_name = 'core/terms.html'


class FAQView(TemplateView):
    """FAQ page."""
    template_name = 'core/faq.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['faq_categories'] = get_faq_categories()
        return context


# =============================================================================
# Search
# =============================================================================

class SearchResultsView(View):
    """Search results page — Advanced Search & Discovery improvement."""
    
    template_name = 'core/search_results.html'
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        page = int(request.GET.get('page', 1) or 1)
        sort = request.GET.get('sort', 'relevance')

        # --- Advanced filters ---
        category_slug = request.GET.get('category')
        category = None
        if category_slug:
            try:
                category = Category.objects.get(slug=category_slug, is_active=True)
            except Category.DoesNotExist:
                category = None

        def f2float(v):
            try:
                return float(v) if v not in (None, '',) else None
            except Exception:
                return None

        min_price = f2float(request.GET.get('min_price'))
        max_price = f2float(request.GET.get('max_price'))
        min_rating = f2float(request.GET.get('min_rating'))
        municipality = request.GET.get('municipality') or None
        ward_number = request.GET.get('ward_number')
        try:
            ward_number = int(ward_number) if ward_number else None
        except Exception:
            ward_number = None

        verified_only = request.GET.get('verified_only') == '1'
        in_stock_only = request.GET.get('in_stock_only', '1') != '0'  # default true
        trusted_only = request.GET.get('trusted_only') == '1'

        # If no query but filters present, allow browse mode
        if len(query) < 2 and not any([category, min_price, max_price, min_rating, municipality, ward_number, verified_only]):
            return render(request, self.template_name, {
                'query': query,
                'results': [],
                'total_count': 0,
                'categories': Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related('children'),
                'suggestions': {},
            })
        
        # Perform advanced search
        results_data = search_products(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            condition=request.GET.get('condition'),
            sort_by=sort,
            page=page,
            per_page=12,
            min_rating=min_rating,
            municipality=municipality,
            ward_number=ward_number,
            verified_only=verified_only or trusted_only,  # trusted implies verified
            in_stock_only=in_stock_only,
        )

        # If trusted_only, further filter in python (since service doesn't have that flag)
        results_list = results_data['results']
        if trusted_only:
            results_list = [p for p in results_list if getattr(p.vendor, 'is_trusted_seller', False)]

        # Get categories for filter — optimized
        categories = Category.objects.filter(is_active=True, parent__isnull=True).prefetch_related('children')[:20]
        
        context = {
            'query': query,
            'results': results_list,
            'total_count': results_data['total_count'],
            'page': results_data['page'],
            'total_pages': results_data['total_pages'],
            'categories': categories,
            'suggestions': results_data.get('suggestions', {}),
            'has_results': results_data.get('has_results', True),
            'applied_filters': results_data.get('applied_filters', {}),
        }
        
        # HTMX partial swap for live filter
        if request.headers.get('HX-Request'):
            return render(request, 'catalog/partials/product_grid.html', context)
        
        return render(request, self.template_name, context)


# =============================================================================
# HTMX Search Suggestions
# =============================================================================

def search_suggestions_htmx(request):
    """Return search suggestions as user types (HTMX)."""
    query = request.GET.get('q', '')
    
    if len(query) < 2:
        return render(request, 'core/partials/search_suggestions.html', {'suggestions': []})
    
    # Get product suggestions
    products = Product.objects.filter(
        is_active=True,
        name__icontains=query
    ).values_list('name', flat=True)[:5]
    
    # Get category suggestions
    categories = Category.objects.filter(
        is_active=True,
        name__icontains=query
    ).values_list('name', flat=True)[:3]
    
    suggestions = {
        'products': list(products),
        'categories': list(categories),
    }
    
    return render(request, 'core/partials/search_suggestions.html', {'suggestions': suggestions})