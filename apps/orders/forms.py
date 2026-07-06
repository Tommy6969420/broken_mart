"""
Forms for orders app.
Handles cart, checkout, order management, and payments.
"""
from django import forms
from django.core.validators import MinValueValidator

from .models import Cart, CartItem, Coupon, Order, OrderItem


class CartItemForm(forms.ModelForm):
    """Form for updating cart item quantity."""
    
    quantity = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-16 px-2 py-1 border-2 border-neutral-300 rounded-stall text-center',
            'min': '1',
            'max': '99',
        }),
        validators=[MinValueValidator(1)],
        initial=1
    )
    
    class Meta:
        model = CartItem
        fields = ('quantity',)


class ApplyCouponForm(forms.Form):
    """Form for applying coupon code."""
    
    code = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition uppercase',
            'placeholder': 'Enter coupon code',
            'maxlength': '20',
        }),
        max_length=20,
        required=True,
        help_text="Enter the coupon code provided by the vendor"
    )
    
    def clean_code(self):
        code = self.cleaned_data.get('code', '').strip().upper()
        return code


class CheckoutForm(forms.Form):
    """Form for checkout with address selection and payment method."""
    
    address = forms.ModelChoiceField(
        queryset=None,  # Set dynamically
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        empty_label="Select delivery address",
        required=True,
        help_text="Choose a delivery address"
    )
    
    use_new_address = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        initial=False,
        label="Use a different address"
    )
    
    payment_method = forms.ChoiceField(
        choices=Order.PaymentMethod.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    special_instructions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'e.g., "Leave at gate", "Call before arriving"',
            'rows': 2,
        }),
        max_length=500
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            from apps.accounts.models import Address
            self.fields['address'].queryset = Address.objects.filter(user=user).order_by('-is_default', '-id')
    
    def clean(self):
        cleaned_data = super().clean()
        address = cleaned_data.get('address')
        
        if not address:
            raise forms.ValidationError("Please select a delivery address.")
        
        # Validate delivery zone
        from apps.accounts.services import validate_delivery_zone
        zone_check = validate_delivery_zone(address)
        if not zone_check.get('deliverable'):
            raise forms.ValidationError(zone_check.get('message', 'Delivery not available to this address.'))
        
        return cleaned_data


class OrderCancelForm(forms.Form):
    """Form for canceling an order."""
    
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Why are you canceling this order?',
            'rows': 3,
        }),
        max_length=500,
        required=True,
        help_text="Please provide a reason for cancellation"
    )
    
    confirm = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        required=True,
        label="I confirm I want to cancel this order"
    )


class ReturnRequestForm(forms.Form):
    """Form for requesting a return."""
    
    reason = forms.ChoiceField(
        choices=[
            ('defective', 'Product is defective/damaged'),
            ('wrong_item', 'Received wrong item'),
            ('not_as_described', 'Not as described'),
            ('changed_mind', 'Changed my mind'),
            ('other', 'Other'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Describe the issue in detail...',
            'rows': 4,
        }),
        max_length=1000,
        required=True
    )
    
    confirm = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        required=True,
        label="I confirm the return request is accurate"
    )


class CouponForm(forms.ModelForm):
    """Form for creating/editing coupons."""
    
    code = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition uppercase',
            'placeholder': 'COUPON2026',
            'maxlength': '20',
        }),
        max_length=20
    )
    
    discount_type = forms.ChoiceField(
        choices=[
            ('percentage', 'Percentage discount'),
            ('fixed', 'Fixed amount (NPR)'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    discount_value = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '10',
            'min': '0',
        }),
        decimal_places=2,
        min_value=0,
        help_text="Percentage (0-100) or fixed amount in NPR"
    )
    
    minimum_order_amount = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '0.00',
            'min': '0',
        }),
        decimal_places=2,
        min_value=0,
        initial=0
    )
    
    max_uses = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Unlimited if empty',
            'min': '1',
        }),
        help_text="Maximum number of times this coupon can be used"
    )
    
    valid_from = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'type': 'datetime-local',
        }),
        help_text="Coupon valid from"
    )
    
    valid_until = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'type': 'datetime-local',
        }),
        help_text="Coupon valid until"
    )
    
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        initial=True
    )
    
    class Meta:
        model = Coupon
        fields = ('code', 'discount_type', 'discount_value', 'minimum_order_amount',
                  'max_uses', 'valid_from', 'valid_until', 'is_active')
    
    def clean(self):
        cleaned_data = super().clean()
        
        discount_type = cleaned_data.get('discount_type')
        discount_value = cleaned_data.get('discount_value')
        
        if discount_type == 'percentage' and discount_value and discount_value > 100:
            raise forms.ValidationError("Percentage discount cannot exceed 100%.")
        
        valid_from = cleaned_data.get('valid_from')
        valid_until = cleaned_data.get('valid_until')
        
        if valid_from and valid_until and valid_until <= valid_from:
            raise forms.ValidationError("Valid until date must be after valid from date.")
        
        return cleaned_data