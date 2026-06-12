let caseId = window.CASE_ID || null;
let noticeDraft = window.NOTICE_DRAFT || '';

function setCaseId(id) {
    caseId = id;
}

function updateNoticePanel(text, highlight) {
    noticeDraft = text;
    const draftEl = document.querySelector('#notice-draft-content .notice-text');
    const hiddenEl = document.getElementById('notice-draft-hidden');
    const previewEl = document.querySelector('.notice-preview');

    if (hiddenEl) hiddenEl.value = text;
    if (draftEl) {
        draftEl.textContent = text;
        if (highlight) {
            draftEl.classList.add('notice-highlight-flash');
            setTimeout(() => draftEl.classList.remove('notice-highlight-flash'), 2000);
        }
    }
    if (previewEl) previewEl.textContent = text;

    const panel = document.getElementById('notice-panel');
    if (panel && highlight && window.Alpine) {
        const data = Alpine.$data(panel);
        if (data) data.updated = true;
    }
}

function sendActionMessage(el) {
    const message = el.dataset.message;
    if (!message) return;

    const input = document.getElementById('chat-input');
    const form = document.getElementById('chat-form');
    if (!input || !form) return;

    input.value = message;
    if (typeof htmx !== 'undefined') {
        htmx.trigger(form, 'submit');
    } else {
        form.requestSubmit();
    }
}

function startLoadingSteps() {
    const container = document.getElementById('chat-messages');
    if (container) {
        container.innerHTML = '';
    }

    let step = 0;
    const interval = setInterval(() => {
        const items = document.querySelectorAll('.step-item');
        items.forEach((item, i) => {
            if (i < step) {
                item.classList.add('complete');
                item.classList.remove('active', 'opacity-40');
                const spinner = item.querySelector('.loading-spinner');
                if (spinner) {
                    spinner.outerHTML = '<svg class="w-5 h-5 text-success" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>';
                }
            } else if (i === step) {
                item.classList.add('active');
                item.classList.remove('opacity-40', 'complete');
            }
        });
        step++;
        if (step > 3) clearInterval(interval);
    }, 1200);
}

function submitClarifyingAnswers(caseId) {
    var answers = [];
    document.querySelectorAll('.clarify-answer').forEach(function(input) {
        var val = input.value.trim();
        if (val) {
            var label = input.closest('div').querySelector('label');
            var question = label ? label.textContent : input.getAttribute('data-key');
            answers.push(question + ': ' + val);
        }
    });
    if (answers.length === 0) return;
    var message = 'Here are my answers to your questions:\n' + answers.join('\n');
    htmx.ajax('POST', '/api/cases/' + caseId + '/chat', {
        values: {message: message, current_notice_draft: window.NOTICE_DRAFT || ''},
        target: '#chat-messages',
        swap: 'beforeend',
        indicator: '#chat-typing'
    });
}

document.addEventListener('htmx:beforeRequest', (e) => {
    const form = e.detail.elt;
    if (form && form.id === 'chat-form') {
        const input = document.getElementById('chat-input');
        if (input && !input.value.trim()) {
            e.preventDefault();
            return;
        }
        if (!caseId) {
            const messages = document.getElementById('chat-messages');
            if (messages) messages.innerHTML = '';
            startLoadingSteps();
        }
    }
});

document.addEventListener('htmx:afterSwap', () => {
    const messages = document.getElementById('chat-messages');
    if (messages) {
        messages.scrollTop = messages.scrollHeight;
    }
    const input = document.getElementById('chat-input');
    if (input) {
        input.value = '';
        input.style.height = 'auto';
    }
});

document.addEventListener('keydown', (e) => {
    const input = document.getElementById('chat-input');
    if (!input || document.activeElement !== input) return;
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const form = document.getElementById('chat-form');
        if (form) htmx.trigger(form, 'submit');
    }
});
