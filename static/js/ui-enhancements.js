/**
 * UI Enhancements: Button states, loading animations, error handling
 */
document.addEventListener('DOMContentLoaded', function() {
    // 1. Prevent ghost clicks on buttons that require loading
    document.querySelectorAll('button[data-requires-auth], .btn-action').forEach(btn => {
        btn.addEventListener('click', function(e) {
            if (this.classList.contains('loading')) {
                e.preventDefault();
                return false;
            }
            
            // Show loading state
            const originalText = this.innerHTML;
            this.classList.add('loading', 'disabled');
            this.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2" role="status"></span>
                Processing...
            `;
            
            // Restore after timeout if no redirect happens
            setTimeout(() => {
                if (this.classList.contains('loading')) {
                    this.classList.remove('loading', 'disabled');
                    this.innerHTML = originalText;
                }
            }, 8000);
        });
    });

    // 2. Form validation with visible errors
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let hasError = false;
            
            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    hasError = true;
                    field.classList.add('is-invalid');
                    
                    // Show error message
                    let errorEl = field.parentNode.querySelector('.invalid-feedback');
                    if (!errorEl) {
                        errorEl = document.createElement('div');
                        errorEl.className = 'invalid-feedback';
                        errorEl.textContent = 'This field is required';
                        field.parentNode.appendChild(errorEl);
                    }
                }
            });
            
            if (hasError) {
                e.preventDefault();
                // Scroll to first error
                const firstError = form.querySelector('.is-invalid');
                if (firstError) firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        });
    });

    // 3. Auto-dismiss toasts
    document.querySelectorAll('.toast').forEach(toast => {
        setTimeout(() => {
            toast.classList.add('fade');
            setTimeout(() => toast.remove(), 300);
        }, 4500);
    });
    
    // 4. HTMX loading indicators
    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        const target = evt.detail.target;
        if (target) {
            target.style.opacity = '0.6';
            target.style.pointerEvents = 'none';
        }
    });
    
    document.body.addEventListener('htmx:afterRequest', function(evt) {
        const target = evt.detail.target;
        if (target) {
            target.style.opacity = '1';
            target.style.pointerEvents = 'auto';
        }
    });
});