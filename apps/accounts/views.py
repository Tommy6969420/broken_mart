"""
Views for accounts app.
Handles user authentication, profile management, addresses, vendor and rider functionality.
"""
import random
import re
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView, View

from .forms import (
    AddressForm, ChangePasswordForm, CustomPasswordResetForm, CustomSetPasswordForm,
    LoginForm, RiderProfileEditForm, RiderRegistrationForm, UserProfileForm,
    UserRegistrationForm, VendorProfileEditForm, VendorRegistrationForm
)
from .models import Address, RiderProfile, User, VendorProfile
from .services import (
    generate_otp, send_otp_sms, verify_otp_code,
    refresh_vendor_stats, refresh_rider_stats
)


# =============================================================================
# Authentication Views
# =============================================================================

class LoginView(View):
    """Handle user login with email authentication."""
    
    template_name = 'accounts/login.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        form = LoginForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = LoginForm(data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            
            # Authenticate with email
            user = authenticate(request, username=email, password=password)
            
            if user is not None:
                if user.is_active:
                    login(request, user)
                    
                    # Get next URL from GET parameters
                    next_url = request.GET.get('next', reverse('core:home'))
                    return redirect(next_url)
                else:
                    messages.error(request, 'Your account has been deactivated. Please contact support.')
            else:
                messages.error(request, 'Invalid email or password. Please try again.')
        
        return render(request, self.template_name, {'form': form})


class RegisterView(View):
    """Handle new user registration."""
    
    template_name = 'accounts/register.html'
    
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('core:home')
        form = UserRegistrationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = UserRegistrationForm(data=request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = User.Role.CUSTOMER
            user.save()
            
            # Generate and send OTP
            otp = generate_otp(user)
            # Uncomment in production with SMS gateway configured
            # send_otp_sms(user.phone_number, otp)
            
            # Store user ID in session for OTP verification
            request.session['pending_user_id'] = user.id
            
            messages.success(request, f'Account created! OTP sent to {user.phone_number}')
            return redirect('accounts:verify_otp')
        
        return render(request, self.template_name, {'form': form})


class VerifyOTPView(View):
    """Verify phone number with OTP code — production hardened."""
    
    template_name = 'accounts/verify_otp.html'
    
    def get_otp_state(self, user):
        """Read OTP attempts from cache — fixes bug where user.otp_attempts field doesn't exist."""
        from django.core.cache import cache
        from django.conf import settings
        cache_key = f"otp:{user.id}"
        cached = cache.get(cache_key) or {}
        attempts = cached.get('attempts', 0)
        max_attempts = settings.OTP_MAX_ATTEMPTS
        return {
            'attempts': attempts,
            'attempts_remaining': max(0, max_attempts - attempts),
            'max_attempts': max_attempts,
        }
    
    def get(self, request):
        pending_user_id = request.session.get('pending_user_id')
        if not pending_user_id:
            messages.warning(request, 'No pending verification found. Please register.')
            return redirect('accounts:register')
        
        user = get_object_or_404(User, id=pending_user_id)
        otp_state = self.get_otp_state(user)
        context = {
            'phone_number': user.phone_number,
            'masked_phone': f"****{user.phone_number[-4:]}" if len(user.phone_number) > 4 else "****",
            'attempts_remaining': otp_state['attempts_remaining'],
            'max_attempts': otp_state['max_attempts'],
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        pending_user_id = request.session.get('pending_user_id')
        if not pending_user_id:
            messages.error(request, 'Verification session expired. Please register again.')
            return redirect('accounts:register')
        
        user = get_object_or_404(User, id=pending_user_id)
        otp_code = request.POST.get('otp', '').strip()
        
        # Input sanitization
        if not otp_code or not otp_code.isdigit() or len(otp_code) != 6:
            messages.error(request, 'Please enter a valid 6-digit OTP.')
            otp_state = self.get_otp_state(user)
            return render(request, self.template_name, {
                'phone_number': user.phone_number,
                'attempts_remaining': otp_state['attempts_remaining'],
            })
        
        if verify_otp_code(user, otp_code):
            user.is_phone_verified = True
            user.save(update_fields=['is_phone_verified'])
            
            # Security: clear session OTP data
            for key in ['pending_user_id', 'otp_expiry']:
                request.session.pop(key, None)
            
            # Audit log
            try:
                from apps.support.services import audit
                audit(user, 'phone_verified', 'User', str(user.id), request.META.get('REMOTE_ADDR'))
            except Exception:
                pass
            
            messages.success(request, 'Phone verified successfully! Welcome to Makwanpur Mart.')
            login(request, user)
            return redirect('core:home')
        else:
            otp_state = self.get_otp_state(user)
            if otp_state['attempts_remaining'] <= 0:
                messages.error(request, 'Maximum OTP attempts exceeded. Please request a new code.')
            else:
                messages.error(request, f'Invalid OTP. {otp_state["attempts_remaining"]} attempts remaining.')
            context = {
                'phone_number': user.phone_number,
                'masked_phone': f"****{user.phone_number[-4:]}",
                'attempts_remaining': otp_state['attempts_remaining'],
            }
            return render(request, self.template_name, context)


class ResendOTPView(View):
    """Resend OTP to user phone."""
    
    def post(self, request):
        pending_user_id = request.session.get('pending_user_id')
        if not pending_user_id:
            return JsonResponse({'success': False, 'message': 'No pending verification'})
        
        user = get_object_or_404(User, id=pending_user_id)
        otp = generate_otp(user)
        # send_otp_sms(user.phone_number, otp)  # Uncomment in production
        
        return JsonResponse({
            'success': True,
            'message': f'OTP resent to {user.phone_number}',
            'expires_in': getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
        })


class LogoutView(View):
    """Handle user logout — POST only for CSRF safety (GET kept for backwards compat with warning)."""
    
    def post(self, request):
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
        return redirect('core:home')

    def get(self, request):
        # Production hardening: logout should be POST, but allow GET with warning in dev
        from django.conf import settings
        if settings.DEBUG:
            logout(request)
            messages.info(request, 'Logged out (GET allowed in DEBUG only). Use POST in production.')
            return redirect('core:home')
        # In production, require POST
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])


# =============================================================================
# Profile Views
# =============================================================================

class ProfileView(LoginRequiredMixin, TemplateView):
    """Display user profile dashboard."""
    
    template_name = 'accounts/profile.html'
    login_url = 'accounts:login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['user'] = user
        context['addresses'] = user.addresses.all()[:5]
        context['order_count'] = user.orders.count()
        context['wishlist_count'] = user.wishlist_items.count()
        
        # Add vendor/rider info if applicable
        if user.role == User.Role.VENDOR and hasattr(user, 'vendor_profile'):
            context['vendor'] = user.vendor_profile
            context['product_count'] = user.vendor_profile.products.count()
        
        if user.role == User.Role.RIDER and hasattr(user, 'rider_profile'):
            context['rider'] = user.rider_profile
        
        return context


class ProfileEditView(LoginRequiredMixin, View):
    """Edit user profile."""
    
    template_name = 'accounts/profile_edit.html'
    
    def get(self, request):
        form = UserProfileForm(instance=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = UserProfileForm(instance=request.user, data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
        
        return render(request, self.template_name, {'form': form})


class ChangePasswordView(LoginRequiredMixin, View):
    """Change user password."""
    
    template_name = 'accounts/change_password.html'
    
    def get(self, request):
        form = ChangePasswordForm(user=request.user)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = ChangePasswordForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Password changed successfully!')
            return redirect('accounts:profile')
        
        return render(request, self.template_name, {'form': form})


class PasswordResetView(View):
    """Request password reset via email."""
    
    template_name = 'accounts/password_reset.html'
    
    def get(self, request):
        form = CustomPasswordResetForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = CustomPasswordResetForm(data=request.POST)
        if form.is_valid():
            form.save(
                subject_template_name='accounts/emails/password_reset_subject.txt',
                email_template_name='accounts/emails/password_reset_email.html',
                from_email=settings.DEFAULT_FROM_EMAIL
            )
            messages.success(request, 'Password reset link sent to your email.')
            return redirect('accounts:login')
        
        return render(request, self.template_name, {'form': form})


class PasswordResetConfirmView(View):
    """Set new password after reset — production fixed."""
    
    template_name = 'accounts/password_reset_confirm.html'
    
    def get_user_from_token(self, uidb64, token):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_decode
        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None
        if default_token_generator.check_token(user, token):
            return user
        return None
    
    def get(self, request, uidb64, token):
        user = self.get_user_from_token(uidb64, token)
        if user is None:
            messages.error(request, 'Invalid or expired reset link. Please request a new one.')
            return redirect('accounts:password_reset')
        form = CustomSetPasswordForm(user=user)
        return render(request, self.template_name, {'form': form, 'validlink': True})
    
    def post(self, request, uidb64, token):
        user = self.get_user_from_token(uidb64, token)
        if user is None:
            messages.error(request, 'Invalid reset link. Please request a new one.')
            return redirect('accounts:password_reset')
        
        form = CustomSetPasswordForm(user=user, data=request.POST)
        if form.is_valid():
            form.save()
            # Security: log password reset
            try:
                from apps.support.services import audit
                audit(user, 'password_reset_confirm', 'User', str(user.id), request.META.get('REMOTE_ADDR'))
            except Exception:
                pass
            messages.success(request, 'Password reset successful! You can now login.')
            return redirect('accounts:login')
        
        return render(request, self.template_name, {'form': form, 'validlink': True})


# =============================================================================
# Address Views
# =============================================================================

class AddressListView(LoginRequiredMixin, ListView):
    """List user's delivery addresses."""
    
    model = Address
    template_name = 'accounts/address_list.html'
    context_object_name = 'addresses'
    paginate_by = 10
    
    def get_queryset(self):
        return Address.objects.filter(user=self.request.user).order_by('-is_default', '-id')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['default_address'] = self.get_queryset().filter(is_default=True).first()
        return context


class AddressCreateView(LoginRequiredMixin, View):
    """Create new delivery address."""
    
    template_name = 'accounts/address_form.html'
    
    def get(self, request):
        form = AddressForm()
        return render(request, self.template_name, {'form': form, 'address': None})
    
    def post(self, request):
        form = AddressForm(data=request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            
            # Unset other default if this is default
            if address.is_default:
                Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
            
            address.save()
            messages.success(request, 'Address added successfully!')
            
            # HTMX request - return partial
            if request.headers.get('HX-Request'):
                return render(request, 'accounts/partials/address_item.html', {'address': address})
            
            return redirect('accounts:address_list')
        
        return render(request, self.template_name, {'form': form, 'address': None})


class AddressUpdateView(LoginRequiredMixin, View):
    """Update existing address."""
    
    template_name = 'accounts/address_form.html'
    
    def get(self, request, pk):
        address = get_object_or_404(Address, pk=pk, user=request.user)
        form = AddressForm(instance=address)
        return render(request, self.template_name, {'form': form, 'address': address})
    
    def post(self, request, pk):
        address = get_object_or_404(Address, pk=pk, user=request.user)
        form = AddressForm(instance=address, data=request.POST)
        if form.is_valid():
            addr = form.save(commit=False)
            
            # Unset other default if this is default
            if addr.is_default:
                Address.objects.filter(user=request.user, is_default=True).exclude(pk=pk).update(is_default=False)
            
            addr.save()
            messages.success(request, 'Address updated successfully!')
            return redirect('accounts:address_list')
        
        return render(request, self.template_name, {'form': form, 'address': address})


@require_POST
@login_required
def address_delete(request, pk):
    """Delete an address via HTMX."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    
    if request.headers.get('HX-Request'):
        addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-id')
        return render(request, 'accounts/partials/address_list.html', {'addresses': addresses})
    
    messages.success(request, 'Address deleted.')
    return redirect('accounts:address_list')


@require_POST
@login_required
def address_set_default(request, pk):
    """Set an address as default."""
    address = get_object_or_404(Address, pk=pk, user=request.user)
    
    # Unset other defaults
    Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
    
    address.is_default = True
    address.save(update_fields=['is_default'])
    
    if request.headers.get('HX-Request'):
        addresses = Address.objects.filter(user=request.user).order_by('-is_default', '-id')
        return render(request, 'accounts/partials/address_list.html', {'addresses': addresses})
    
    messages.success(request, 'Default address updated.')
    return redirect('accounts:address_list')


# =============================================================================
# Vendor Views
# =============================================================================

class VendorRegisterView(LoginRequiredMixin, View):
    """Register as a vendor."""
    
    template_name = 'accounts/vendor_register.html'
    
    def get(self, request):
        if request.user.role == User.Role.VENDOR:
            return redirect('accounts:vendor_status')
        
        form = VendorRegistrationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = VendorRegistrationForm(data=request.POST, files=request.FILES)
        if form.is_valid():
            vendor = form.save(commit=False)
            vendor.user = request.user
            vendor.save()
            
            # Update user role
            request.user.role = User.Role.VENDOR
            request.user.save(update_fields=['role'])
            
            messages.success(request, 'Vendor registration submitted! Your application is under review.')
            return redirect('accounts:vendor_status')
        
        return render(request, self.template_name, {'form': form})


class VendorAgreementView(TemplateView):
    """Display vendor agreement."""
    
    template_name = 'accounts/vendor_agreement.html'


class VendorStatusView(LoginRequiredMixin, TemplateView):
    """Show vendor application status."""
    
    template_name = 'accounts/vendor_status.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if hasattr(self.request.user, 'vendor_profile'):
            context['vendor'] = self.request.user.vendor_profile
        return context


class VendorDashboardView(LoginRequiredMixin, TemplateView):
    """Vendor dashboard with stats and actions."""
    
    template_name = 'accounts/vendor_dashboard.html'
    login_url = 'accounts:login'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if not hasattr(self.request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        vendor = self.request.user.vendor_profile
        context['vendor'] = vendor
        context['products'] = vendor.products.filter(is_active=True).order_by('-created_at')[:10]
        context['recent_orders'] = vendor.order_items.select_related('order').order_by('-order__placed_at')[:5]
        
        # Stats
        total_sales = vendor.order_items.filter(
            item_status='delivered'
        ).aggregate(total=Sum('unit_price'))['total'] or 0
        
        context['stats'] = {
            'total_products': vendor.products.count(),
            'total_sales': total_sales,
            'pending_orders': vendor.order_items.filter(item_status__in=['pending', 'confirmed', 'preparing']).count(),
            'average_rating': vendor.average_rating,
        }
        
        return context


class VendorProfileEditView(LoginRequiredMixin, View):
    """Edit vendor profile."""
    
    template_name = 'accounts/vendor_profile_edit.html'
    
    def get(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        form = VendorProfileEditForm(instance=request.user.vendor_profile)
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        if not hasattr(request.user, 'vendor_profile'):
            raise PermissionDenied("You are not a vendor.")
        
        form = VendorProfileEditForm(instance=request.user.vendor_profile, data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Shop profile updated!')
            return redirect('accounts:vendor_dashboard')
        
        return render(request, self.template_name, {'form': form})


# =============================================================================
# Rider Views
# =============================================================================

class RiderRegisterView(LoginRequiredMixin, View):
    """Register as a delivery rider."""
    
    template_name = 'accounts/rider_register.html'
    
    def get(self, request):
        if request.user.role == User.Role.RIDER:
            return redirect('accounts:rider_dashboard')
        
        form = RiderRegistrationForm()
        return render(request, self.template_name, {'form': form})
    
    def post(self, request):
        form = RiderRegistrationForm(data=request.POST)
        if form.is_valid():
            rider = form.save(commit=False)
            rider.user = request.user
            rider.save()
            
            request.user.role = User.Role.RIDER
            request.user.save(update_fields=['role'])
            
            messages.success(request, 'Rider registration submitted!')
            return redirect('accounts:rider_dashboard')
        
        return render(request, self.template_name, {'form': form})


class RiderDashboardView(LoginRequiredMixin, TemplateView):
    """Rider dashboard — KYC gated — riders can ONLY take tasks after being verified."""
    
    template_name = 'accounts/rider_dashboard.html'
    login_url = 'accounts:login'
    
    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'rider_profile'):
            messages.warning(request, 'Rider profile required — register as delivery partner.')
            return redirect('accounts:rider_register')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        rider = self.request.user.rider_profile
        
        # KYC VERIFICATION GATE — Requirement #6
        if not rider.can_accept_deliveries:
            messages.warning(
                self.request,
                f'KYC {rider.get_kyc_status_display()} — Complete KYC verification to accept Hetauda deliveries. '
                'Upload: citizenship, license, bluebook, selfie.'
            )
            context['kyc_blocked'] = True
            context['kyc_status'] = rider.kyc_status
            context['kyc_form_needed'] = rider.kyc_status in ['not_submitted', 'rejected']
            available_deliveries = []
        else:
            # Get available deliveries in zone — optimized
            if rider.current_zone:
                available_deliveries = rider.current_zone.deliveries.filter(
                    status='unassigned'
                ).select_related(
                    'order', 'order__customer', 'order__delivery_address'
                ).prefetch_related('order__items')[:20]
            else:
                available_deliveries = []
        
        context['rider'] = rider
        context['available_deliveries'] = available_deliveries
        context['my_deliveries'] = rider.deliveries.select_related(
            'order', 'order__customer', 'order__delivery_address'
        ).order_by('-assigned_at')[:10]
        
        # Stats — with KYC status
        context['stats'] = {
            'total_deliveries': rider.total_deliveries,
            'available': rider.is_available and rider.can_accept_deliveries,
            'current_zone': rider.current_zone.name if rider.current_zone else 'Not set',
            'kyc_status': rider.get_kyc_status_display(),
            'kyc_verified': rider.is_kyc_verified,
            'can_accept': rider.can_accept_deliveries,
            'rating': float(rider.average_delivery_rating),
        }

        # KYC progress
        kyc_docs = {
            'citizenship_front': bool(rider.citizenship_front_image),
            'citizenship_back': bool(rider.citizenship_back_image),
            'license': bool(rider.license_image) if rider.vehicle_type == 'bike' else True,
            'bluebook': bool(rider.vehicle_bluebook_image) if rider.vehicle_type == 'bike' else True,
            'selfie': bool(rider.selfie_with_id),
        }
        context['kyc_docs'] = kyc_docs
        context['kyc_progress'] = int(sum(kyc_docs.values()) / len(kyc_docs) * 100)
        
        return context


class RiderProfileEditView(LoginRequiredMixin, View):
    """Edit rider profile."""
    
    template_name = 'accounts/rider_profile_edit.html'
    
    def get(self, request):
        if not hasattr(request.user, 'rider_profile'):
            raise PermissionDenied("You are not a rider.")
        
        form = RiderProfileEditForm(instance=request.user.rider_profile)
        return render(request, self.template_name, {'form': form, 'rider': request.user.rider_profile})
    
    def post(self, request):
        if not hasattr(request.user, 'rider_profile'):
            raise PermissionDenied("You are not a rider.")
        
        form = RiderProfileEditForm(instance=request.user.rider_profile, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated!')
            return redirect('accounts:rider_dashboard')
        
        return render(request, self.template_name, {'form': form, 'rider': request.user.rider_profile})


# =============================================================================
# HTMX Partial Views
# =============================================================================

@login_required
def profile_dropdown_partial(request):
    """Return profile dropdown for HTMX update."""
    user = request.user
    return render(request, 'accounts/partials/profile_dropdown.html', {'user': user})