document.addEventListener('htmx:afterSwap', (e) => {
    if (e.detail.target && e.detail.target.id === 'pdf-result') {
        const link = e.detail.target.querySelector('a[target="_blank"]');
        if (link) {
            setTimeout(() => link.focus(), 100);
        }
    }
});
