function showNotification(message, type = 'info') {
    const container = document.getElementById('flash-messages') || createContainer();
    const alert = document.createElement('div');
    alert.className = `alert alert-${type === 'error' ? 'error' : 'info'} shadow-lg max-w-sm animate-fade-in`;
    alert.innerHTML = `<span>${message}</span>`;
    container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}

function createContainer() {
    const container = document.createElement('div');
    container.id = 'flash-messages';
    container.className = 'fixed top-4 right-4 z-50 space-y-2';
    document.body.appendChild(container);
    return container;
}

setTimeout(() => {
    document.querySelectorAll('#flash-messages .alert').forEach((el) => el.remove());
}, 5000);
