"""
Forms for accounts app.
Handles user registration, authentication, profile management, addresses, vendor and rider registration.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.validators import RegexValidator
from django.db.models import Q

from .models import User, Address, VendorProfile, RiderProfile


class UserRegistrationForm(UserCreationForm):
    """Registration form with Nepali phone validation."""
    
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'your@email.com',
        }),
        help_text="This will be your login ID"
    )
    
    username = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Username for display',
        }),
        min_length=3,
        max_length=30
    )
    
    phone_number = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '+97798XXXXXXXX',
            'inputmode': 'tel',
        }),
        validators=[RegexValidator(
            r'^(\+?977?9)?\d{9}$',
            message="Enter a valid Nepali mobile number (e.g., +9779841234567)"
        )],
        help_text="Enter without spaces, starting with +977 or 0"
    )
    
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '••••••••',
        }),
        label="Password"
    )
    
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '••••••••',
        }),
        label="Confirm Password"
    )
    
    class Meta:
        model = User
        fields = ('email', 'username', 'phone_number', 'password1', 'password2')
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email.lower()
    
    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        # Normalize to +977 format
        if phone:
            phone = phone.replace(' ', '').replace('-', '')
            if not phone.startswith('+'):
                if phone.startswith('0'):
                    phone = '+977' + phone[1:]
                else:
                    phone = '+977' + phone
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError("An account with this phone number already exists.")
        return phone
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email'].lower()
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Custom login form with email-based authentication."""
    
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'your@email.com',
            'autofocus': True,
        }),
        label="Email"
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '••••••••',
        })
    )
    
    error_messages = {
        'invalid_login': 'Please enter a valid email and password.',
        'inactive': 'This account is inactive. Please contact support.',
    }


class UserProfileForm(forms.ModelForm):
    """Form for editing user profile."""
    
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        disabled=True,
        help_text="Username cannot be changed"
    )
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition bg-neutral-100',
        }),
        disabled=True,
        help_text="Contact support to change email"
    )
    
    phone_number = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'inputmode': 'tel',
        }),
        validators=[RegexValidator(r'^(\+?977?9)?\d{9}$', "Invalid Nepali mobile number")]
    )
    
    preferred_language = forms.ChoiceField(
        choices=User.Language.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input w-full border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'accept': 'image/*',
        }),
        help_text="Upload a clear photo (max 5MB)"
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'phone_number', 'preferred_language', 'profile_picture')
    
    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone:
            phone = phone.replace(' ', '').replace('-', '')
            if not phone.startswith('+'):
                if phone.startswith('0'):
                    phone = '+977' + phone[1:]
                else:
                    phone = '+977' + phone
            # Check if phone exists for another user
            if User.objects.filter(phone_number=phone).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("This phone number is already in use.")
        return phone


class ChangePasswordForm(PasswordChangeForm):
    """Custom password change form with styled widgets."""
    
    old_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Current password',
            'autocomplete': 'current-password',
            'autofocus': True,
        })
    )
    
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'New password',
            'autocomplete': 'new-password',
        })
    )
    
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
    )


class CustomPasswordResetForm(PasswordResetForm):
    """Password reset form with styled widgets."""
    
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'your@email.com',
            'autocomplete': 'email',
        })
    )
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not User.objects.filter(email__iexact=email).exists():
            # Don't reveal that the email doesn't exist
            return email
        return email


class CustomSetPasswordForm(SetPasswordForm):
    """Set new password form with styled widgets."""
    
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'New password',
            'autocomplete': 'new-password',
        })
    )
    
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        })
    )


class AddressForm(forms.ModelForm):
    """Form for managing delivery addresses."""
    
    label = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Home, Office, Shop...',
        }),
        max_length=50,
        help_text="A short label to identify this address"
    )
    
    full_address = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'House/building number, street (if any)',
            'rows': 2,
        })
    )
    
    landmark = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Near traffic Chowk, beside the school...',
        }),
        help_text="Helps delivery riders find you faster"
    )
    
    municipality = forms.ChoiceField(
        choices=Address.Municipality.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    ward_number = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': '1-19',
            'min': 1,
            'max': 19,
        }),
        help_text="Ward number (1-19)"
    )
    
    is_default = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        label="Set as default address"
    )
    
    latitude = forms.DecimalField(
        required=False,
        widget=forms.HiddenInput()
    )
    
    longitude = forms.DecimalField(
        required=False,
        widget=forms.HiddenInput()
    )
    
    class Meta:
        model = Address
        fields = ('label', 'full_address', 'landmark', 'municipality', 'ward_number', 'is_default', 'latitude', 'longitude')
    
    def clean_ward_number(self):
        ward = self.cleaned_data.get('ward_number')
        if ward and (ward < 1 or ward > 19):
            raise forms.ValidationError("Ward number must be between 1 and 19.")
        return ward
    
    def clean(self):
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        lat = cleaned_data.get('latitude')
        lon = cleaned_data.get('longitude')
        if lat is not None and lon is not None:
            from decimal import Decimal
            if not (Decimal('27.15') <= lat <= Decimal('27.65') and Decimal('84.65') <= lon <= Decimal('85.35')):
                raise forms.ValidationError("Exact pinpointed coordinates must be inside Makwanpur District, Nepal (Lat: 27.15 - 27.65, Lon: 84.65 - 85.35).")
        
        # If this is set as default, unset other defaults for this user
        # Fix: use instance.user not self.initial.get('user')
        user = getattr(self.instance, 'user', None)
        if is_default and user and user.pk:
            Address.objects.filter(
                user=user,
                is_default=True
            ).exclude(pk=self.instance.pk or 0).update(is_default=False)
        
        return cleaned_data


class VendorRegistrationForm(forms.ModelForm):
    """Form for vendor registration."""
    
    shop_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Your shop or business name',
        }),
        max_length=120,
        help_text="This will be displayed on your storefront"
    )
    
    shop_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Tell customers about your business...',
            'rows': 3,
        })
    )
    
    shop_logo = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input w-full border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'accept': 'image/*',
        }),
        help_text="Upload your shop logo (optional)"
    )
    
    category = forms.ModelChoiceField(
        queryset=None,  # Set dynamically in __init__
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        empty_label="Select primary category",
        help_text="Choose the main category for your products"
    )
    
    payout_method = forms.ChoiceField(
        choices=VendorProfile.PayoutMethod.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    payout_account_details = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'For eSewa: 98XXXXXXXX\nFor Khalti: 98XXXXXXXX\nFor Bank: Account name, Bank, Account No.',
            'rows': 3,
        }),
        help_text="Your payment account details for receiving payouts"
    )
    
    agreement_accepted = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        required=True,
        label="I agree to the Vendor Terms and Conditions"
    )
    
    class Meta:
        model = VendorProfile
        fields = ('shop_name', 'shop_description', 'shop_logo', 'category', 'payout_method', 'payout_account_details')
    
    def __init__(self, *args, **kwargs):
        from apps.catalog.models import Category
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
    
    def clean(self):
        cleaned_data = super().clean()
        agreement = cleaned_data.get('agreement_accepted')
        if not agreement:
            raise forms.ValidationError("You must accept the vendor agreement to proceed.")
        return cleaned_data


class VendorProfileEditForm(forms.ModelForm):
    """Form for editing vendor profile."""
    
    shop_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        }),
        max_length=120
    )
    
    shop_description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'rows': 3,
        })
    )
    
    shop_logo = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-input w-full border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'accept': 'image/*',
        })
    )
    
    payout_method = forms.ChoiceField(
        choices=VendorProfile.PayoutMethod.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    payout_account_details = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'rows': 3,
        })
    )
    
    class Meta:
        model = VendorProfile
        fields = ('shop_name', 'shop_description', 'shop_logo', 'payout_method', 'payout_account_details')


class RiderRegistrationForm(forms.ModelForm):
    """Form for rider registration."""
    
    vehicle_type = forms.ChoiceField(
        choices=RiderProfile.VehicleType.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    class Meta:
        model = RiderProfile
        fields = ('vehicle_type',)


class RiderProfileEditForm(forms.ModelForm):
    """Form for editing rider profile — with KYC (Marketplace Improvement #6)."""
    
    vehicle_type = forms.ChoiceField(
        choices=RiderProfile.VehicleType.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    is_available = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-2 border-neutral-300 focus:border-brand-marigold',
        }),
        label="Available for deliveries — requires KYC verified",
        help_text="Auto-disabled if KYC not verified"
    )

    # --- KYC fields ---
    citizenship_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class':'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall','placeholder':'27-01-76-XXXXX'}))
    citizenship_front_image = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class':'form-input w-full border rounded-stall','accept':'image/*'}))
    citizenship_back_image = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class':'form-input w-full border rounded-stall','accept':'image/*'}))
    license_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class':'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall','placeholder':'License No.'}))
    license_image = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class':'form-input w-full border rounded-stall','accept':'image/*'}))
    vehicle_registration_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class':'form-input w-full px-4 py-2 border rounded-stall','placeholder':'Ba 19 Pa XXXX'}))
    vehicle_bluebook_image = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class':'form-input w-full border rounded-stall','accept':'image/*'}))
    selfie_with_id = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class':'form-input w-full border rounded-stall','accept':'image/*'}), help_text="Selfie holding citizenship — liveness check")
    emergency_contact_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class':'form-input w-full px-4 py-2 border rounded-stall'}))
    emergency_contact_phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class':'form-input w-full px-4 py-2 border rounded-stall','placeholder':'+97798XXXXXXXX'}))
    permanent_address = forms.CharField(required=False, widget=forms.Textarea(attrs={'class':'form-input w-full px-4 py-2 border rounded-stall','rows':2}))
    current_municipality = forms.ChoiceField(choices=Address.Municipality.choices, required=False, widget=forms.Select(attrs={'class':'form-select w-full px-4 py-2 border rounded-stall'}))
    current_ward = forms.IntegerField(required=False, min_value=1, max_value=19, widget=forms.NumberInput(attrs={'class':'form-input w-full px-4 py-2 border rounded-stall'}))
    
    class Meta:
        model = RiderProfile
        fields = (
            'vehicle_type', 'is_available',
            # KYC
            'citizenship_number', 'citizenship_front_image', 'citizenship_back_image',
            'license_number', 'license_image',
            'vehicle_registration_number', 'vehicle_bluebook_image',
            'selfie_with_id',
            'emergency_contact_name', 'emergency_contact_phone',
            'permanent_address', 'current_municipality', 'current_ward',
        )

    def clean(self):
        cleaned = super().clean()
        # if trying to go available, enforce KYC
        is_available = cleaned.get('is_available')
        if is_available and self.instance and not self.instance.can_accept_deliveries:
            # Check if KYC docs being submitted now
            has_cit_front = cleaned.get('citizenship_front_image') or self.instance.citizenship_front_image
            has_cit_back = cleaned.get('citizenship_back_image') or self.instance.citizenship_back_image
            has_selfie = cleaned.get('selfie_with_id') or self.instance.selfie_with_id
            if not (has_cit_front and has_cit_back and has_selfie):
                raise forms.ValidationError(
                    "KYC documents required before going online: citizenship front/back + selfie with ID. "
                    "Upload documents — status will change to 'Pending Verification', admin reviews within 24h."
                )
            # auto-submit KYC if docs present
            cleaned['kyc_status'] = RiderProfile.KYCStatus.PENDING
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        # If KYC docs just uploaded, move to PENDING
        has_all_docs = bool(
            obj.citizenship_front_image and obj.citizenship_back_image and obj.selfie_with_id
        )
        if has_all_docs and obj.kyc_status == RiderProfile.KYCStatus.NOT_SUBMITTED:
            from django.utils import timezone
            obj.kyc_status = RiderProfile.KYCStatus.PENDING
            obj.kyc_submitted_at = timezone.now()
        if commit:
            obj.save()
        return obj