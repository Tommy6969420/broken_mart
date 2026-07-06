"""
Forms for support app.
Handles help center, complaints, and notifications.
"""
from django import forms

from .models import GrievanceComplaint, Notification


class GrievanceComplaintForm(forms.ModelForm):
    """Form for filing a grievance complaint."""
    
    category = forms.ChoiceField(
        choices=GrievanceComplaint.Category.choices,
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Describe your issue in detail...',
            'rows': 5,
        }),
        max_length=2000,
        help_text="Please provide as much detail as possible"
    )
    
    class Meta:
        model = GrievanceComplaint
        fields = ('category', 'description')


class NotificationForm(forms.ModelForm):
    """Form for creating notifications (admin only)."""
    
    class Meta:
        model = Notification
        fields = ('user', 'type', 'title', 'message', 'sent_via')


class ComplaintResolutionForm(forms.ModelForm):
    """Form for resolving a complaint (admin only)."""
    
    resolution_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-input w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
            'placeholder': 'Enter resolution details...',
            'rows': 4,
        }),
        max_length=1000
    )
    
    status = forms.ChoiceField(
        choices=[
            ('in_review', 'In Review'),
            ('resolved', 'Resolved'),
            ('escalated', 'Escalated'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-select w-full px-4 py-2 border-2 border-neutral-300 rounded-stall focus:border-brand-marigold focus:outline-none transition',
        })
    )
    
    class Meta:
        model = GrievanceComplaint
        fields = ('resolution_notes', 'status')