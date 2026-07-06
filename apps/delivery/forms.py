"""
Forms for delivery app.
Handles delivery zone management and delivery assignments.
"""
from django import forms

from .models import Delivery, DeliveryZone


class DeliveryZoneForm(forms.ModelForm):
    """Form for creating/editing delivery zones."""
    
    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'e.g., Hetauda Central',
        }),
        max_length=80
    )
    
    ward_numbers = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'e.g., 1, 2, 3, 4, 5',
        }),
        help_text="Comma-separated ward numbers"
    )
    
    base_delivery_fee = forms.DecimalField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '50',
            'step': '0.01',
            'min': '0',
        }),
        decimal_places=2,
        min_value=0,
        help_text="Delivery fee in NPR"
    )
    
    estimated_delivery_time_minutes = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '30',
            'min': '5',
            'max': '180',
        }),
        min_value=5,
        max_value=180,
        help_text="Estimated delivery time in minutes"
    )
    
    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        initial=True
    )
    
    class Meta:
        model = DeliveryZone
        fields = ('name', 'ward_numbers', 'base_delivery_fee', 'estimated_delivery_time_minutes', 'is_active')
    
    def clean_ward_numbers(self):
        ward_str = self.cleaned_data.get('ward_numbers', '')
        try:
            wards = [int(w.strip()) for w in ward_str.split(',') if w.strip()]
            if not wards:
                raise ValueError()
            return wards
        except ValueError:
            raise forms.ValidationError("Enter comma-separated ward numbers (e.g., 1, 2, 3)")


class DeliveryAssignmentForm(forms.ModelForm):
    """Form for assigning a delivery to a rider."""
    
    rider = forms.ModelChoiceField(
        queryset=None,  # Set dynamically
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        empty_label="Select rider",
        required=False
    )
    
    class Meta:
        model = Delivery
        fields = ('rider',)
    
    def __init__(self, *args, **kwargs):
        from apps.accounts.models import RiderProfile
        
        super().__init__(*args, **kwargs)
        # Get available riders
        self.fields['rider'].queryset = RiderProfile.objects.filter(
            is_available=True
        ).select_related('user', 'current_zone')


class DeliveryStatusUpdateForm(forms.ModelForm):
    """Form for updating delivery status."""
    
    failure_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Why could the delivery not be completed?',
            'rows': 2,
        }),
        max_length=500
    )
    
    class Meta:
        model = Delivery
        fields = ('status', 'failure_reason')
    
    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get('status')
        failure_reason = cleaned_data.get('failure_reason', '')
        
        if status == 'failed' and not failure_reason:
            raise forms.ValidationError("Please provide a reason for the failed delivery.")
        
        return cleaned_data