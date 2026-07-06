"""
Google OAuth adapters — Makwanpur Mart
Makes allauth work with custom User model (email USERNAME_FIELD, phone_number required)
"""
from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
import logging

logger = logging.getLogger('apps.accounts.oauth')

class MakwanpurAccountAdapter(DefaultAccountAdapter):
    """Custom account adapter — auto-fill phone placeholder for Google users."""
    
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        # ensure role defaults
        if not user.role:
            user.role = 'customer'
        # phone_number is required & unique in our User model — generate placeholder, force user to update later
        if not user.phone_number:
            import random
            # placeholder that passes regex: 98XXXXXXXX
            # ensure uniqueness
            from .models import User as U
            while True:
                candidate = f"+97798{random.randint(600000000,699999999)}"
                if not U.objects.filter(phone_number=candidate).exists():
                    user.phone_number = candidate
                    break
            user.is_phone_verified = False
        if commit:
            user.save()
        return user


class MakwanpurSocialAdapter(DefaultSocialAccountAdapter):
    """Google OAuth → auto-connect to existing email user, set role=customer, generate phone placeholder."""
    
    def is_auto_signup_allowed(self, request, sociallogin):
        return True

    def pre_social_login(self, request, sociallogin):
        """Connect Google account to existing email user — easy account creation."""
        email = sociallogin.account.extra_data.get('email', '').lower()
        if email:
            from .models import User
            try:
                user = User.objects.get(email__iexact=email)
                # connect
                if sociallogin.is_existing:
                    return
                sociallogin.connect(request, user)
                logger.info(f"Google OAuth auto-connected to existing user {email}")
            except User.DoesNotExist:
                pass
            except Exception as e:
                logger.error(f"Google pre_social_login error: {e}")

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        # ensure custom fields
        if not user.role:
            user.role = 'customer'
        # phone_number required — generate placeholder, prompt verify later
        if not user.phone_number or User.objects.filter(phone_number=user.phone_number).exclude(pk=user.pk).exists():
            import random
            from .models import User as U
            for _ in range(20):
                candidate = f"+97798{random.randint(600000000,699999999)}"
                if not U.objects.filter(phone_number=candidate).exists():
                    user.phone_number = candidate
                    break
        user.is_phone_verified = False  # force OTP verify post-Google
        # username fallback
        if not user.username:
            base = user.email.split('@')[0][:30]
            from .models import User as U
            username = base
            n=1
            while U.objects.filter(username=username).exclude(pk=user.pk).exists():
                username = f"{base}{n}"
                n+=1
                if n>99: break
            user.username = username
        user.save()
        logger.info(f"Google OAuth new user created: {user.email} / {user.phone_number}")
        return user

    def populate_user(self, request, sociallogin, data):
        """Map Google profile → User fields."""
        user = super().populate_user(request, sociallogin, data)
        extra = sociallogin.account.extra_data
        # names
        if extra.get('given_name') and not user.first_name:
            user.first_name = extra['given_name'][:30]
        if extra.get('family_name') and not user.last_name:
            user.last_name = extra['family_name'][:30]
        # email is USERNAME_FIELD — allauth already sets
        return user
