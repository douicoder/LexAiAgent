document.addEventListener('DOMContentLoaded', () => {
    const activeCase = document.querySelector('.case-item.bg-blue-50');
    if (activeCase) {
        activeCase.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
});
