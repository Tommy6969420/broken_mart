"""
Forms for catalog app.
Handles product management, reviews, wishlist, and vendor product operations.
"""
from django import forms
from django.core.validators import MinValueValidator
from django.db.models import Q

from .models import Category, Product, ProductImage, ProductVariant, Review, Wishlist


class CategoryForm(forms.ModelForm):
    """Form for creating/editing categories."""
    
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Category name',
        }),
        max_length=100
    )
    
    slug = forms.SlugField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'category-slug',
        }),
        max_length=100,
        help_text="Auto-generated from name if left empty"
    )
    
    parent = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        empty_label="No parent (top-level)"
    )
    
    icon = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input w-full border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'accept': 'image/*',
        })
    )
    
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        initial=True
    )
    
    class Meta:
        model = Category
        fields = ('name', 'slug', 'parent', 'icon', 'is_active')


class ProductForm(forms.ModelForm):
    """Form for creating/editing products."""
    
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Product name',
        }),
        max_length=200
    )
    
    category = forms.ModelChoiceField(
        queryset=None,  # Set dynamically
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        empty_label="Select category"
    )
    
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Detailed product description...',
            'rows': 4,
        })
    )
    
    price = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '0.00',
            'step': '0.01',
            'min': '0',
        }),
        decimal_places=2,
        min_value=0,
        help_text="Price in NPR"
    )
    
    discounted_price = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Leave empty if no discount',
            'step': '0.01',
            'min': '0',
        }),
        decimal_places=2,
        min_value=0
    )
    
    stock_quantity = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '0',
            'min': '0',
        }),
        initial=0,
        validators=[MinValueValidator(0)],
        help_text="Total stock across all variants"
    )
    
    sku = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Auto-generated if empty',
        }),
        max_length=64
    )
    
    condition = forms.ChoiceField(
        choices=Product.Condition.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        initial=True
    )
    
    class Meta:
        model = Product
        fields = ('name', 'category', 'description', 'price', 'discounted_price',
                  'stock_quantity', 'sku', 'condition', 'is_active')
    
    def __init__(self, *args, **kwargs):
        from apps.catalog.models import Category
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        price = cleaned_data.get('price')
        discounted_price = cleaned_data.get('discounted_price')
        
        if discounted_price and discounted_price >= price:
            raise forms.ValidationError("Discounted price must be less than original price.")
        
        return cleaned_data


class ProductVariantForm(forms.ModelForm):
    """Form for creating/editing product variants."""
    
    size = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'S, M, L, XL...',
        }),
        max_length=20
    )
    
    color = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Red, Blue, Green...',
        }),
        max_length=30
    )
    
    stock_quantity = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'min': '0',
        }),
        initial=0,
        validators=[MinValueValidator(0)]
    )
    
    price_override = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'step': '0.01',
            'min': '0',
        }),
        decimal_places=2,
        min_value=0
    )
    
    class Meta:
        model = ProductVariant
        fields = ('size', 'color', 'stock_quantity', 'price_override')
    
    def clean(self):
        cleaned_data = super().clean()
        size = cleaned_data.get('size')
        color = cleaned_data.get('color')
        
        if not size and not color:
            raise forms.ValidationError("At least one of size or color is required.")
        
        return cleaned_data


class ProductImageForm(forms.ModelForm):
    """Form for uploading product images."""
    
    image = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'form-input w-full border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'accept': 'image/*',
        }),
        help_text="Upload product image (max 5MB)"
    )
    
    is_primary = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        initial=False,
        label="Set as primary image"
    )
    
    order = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        initial=0
    )
    
    class Meta:
        model = ProductImage
        fields = ('image', 'is_primary', 'order')


class ReviewForm(forms.ModelForm):
    """Form for submitting product reviews."""
    
    rating = forms.IntegerField(
        widget=forms.HiddenInput(),
        min_value=1,
        max_value=5
    )
    
    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Share your experience with this product...',
            'rows': 4,
        })
    )
    
    class Meta:
        model = Review
        fields = ('rating', 'comment')


class ProductSearchForm(forms.Form):
    """Form for product search."""
    
    q = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Search products...',
        }),
        max_length=200,
        required=True,
        min_length=2
    )
    
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        empty_label="All categories"
    )
    
    min_price = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Min price',
            'step': '0.01',
        }),
        min_value=0
    )
    
    max_price = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Max price',
            'step': '0.01',
        }),
        min_value=0
    )
    
    condition = forms.ChoiceField(
        choices=[('', 'Any condition')] + list(Product.Condition.choices),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    sort = forms.ChoiceField(
        choices=[
            ('newest', 'Newest first'),
            ('price_low', 'Price: Low to High'),
            ('price_high', 'Price: High to Low'),
            ('rating', 'Highest rated'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        initial='newest'
    )


class WishlistForm(forms.ModelForm):
    """Form for wishlist items (auto-handled)."""
    
    class Meta:
        model = Wishlist
        fields = ('product',)