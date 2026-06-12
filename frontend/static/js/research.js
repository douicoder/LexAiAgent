document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('form[hx-get]');
    if (!form) return;

    form.addEventListener('submit', () => {
        const results = document.getElementById('search-results');
        if (results && !results.querySelector('.law-card')) {
            results.innerHTML = '<div class="skeleton h-32 w-full rounded-2xl mb-4"></div><div class="skeleton h-32 w-full rounded-2xl"></div>';
        }
    });
});
