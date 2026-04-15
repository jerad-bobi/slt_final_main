const dictionaryShell = document.querySelector('.dictionary-shell');
const dictionaryForm = document.getElementById('dictionary-search-form');
const dictionaryInput = document.getElementById('dictionary-search-input');
const dictionaryResultsBody = document.getElementById('dictionary-results-body');
const dictionaryResultsMeta = document.getElementById('dictionary-results-meta');
const dictionaryResultsTitle = document.getElementById('dictionary-results-title');
const dictionaryLookupUrl = dictionaryShell ? dictionaryShell.dataset.lookupUrl : '';
const dictionaryHistoryUrl = dictionaryShell ? dictionaryShell.dataset.historyUrl : '';
const dictionaryClearHistoryUrl = dictionaryShell ? dictionaryShell.dataset.clearHistoryUrl : '';
const dictionaryHistorySection = document.getElementById('dictionary-history-section');
const dictionaryHistoryBody = document.getElementById('dictionary-history-body');
const clearHistoryBtn = document.getElementById('clear-history-btn');

let dictionaryController = null;
let dictionaryCompiledVideo = null;
let dictionaryCompiledSequence = [];
let dictionaryCompiledIndex = 0;

function sanitizeDictionaryQuery(value) {
    return String(value || '').trim().split(/\s+/)[0] || '';
}

function renderDictionaryEmptyState() {
    if (!dictionaryResultsBody || !dictionaryResultsMeta) {
        return;
    }

    resetDictionaryCompiledPlayback();

    dictionaryResultsMeta.textContent = 'Idle';
    dictionaryResultsTitle.textContent = 'Results';
    dictionaryResultsBody.innerHTML = `
        <div class="dictionary-empty-state">
            Search a word to see sign results.
        </div>
    `;
}

function renderDictionaryLoadingState() {
    if (!dictionaryResultsBody || !dictionaryResultsMeta) {
        return;
    }

    resetDictionaryCompiledPlayback();

    dictionaryResultsMeta.textContent = '⌕';
    dictionaryResultsBody.innerHTML = `
        <div class="dictionary-loading-list" aria-hidden="true">
            <div class="dictionary-loading-card"></div>
            <div class="dictionary-loading-card"></div>
        </div>
    `;
}

function renderDictionaryErrorState() {
    if (!dictionaryResultsBody || !dictionaryResultsMeta) {
        return;
    }

    resetDictionaryCompiledPlayback();

    dictionaryResultsMeta.textContent = '!';
    dictionaryResultsBody.innerHTML = `
        <div class="dictionary-empty-state">
            Sign results unavailable.
        </div>
    `;
}

function renderDictionaryResults(query, payload) {
    if (!dictionaryResultsBody || !dictionaryResultsMeta || !dictionaryResultsTitle) {
        return;
    }

    const entries = payload.entries || [];
    const foundEntries = entries.filter((entry) => entry.found && entry.videos.length);

    dictionaryResultsTitle.textContent = query;

    if (!entries.length || !foundEntries.length) {
        dictionaryResultsMeta.textContent = 'No match';
        dictionaryResultsBody.innerHTML = `
            <div class="dictionary-empty-state">
                No sign result for <strong>${escapeHtml(query)}</strong>.
            </div>
        `;
        return;
    }

    const strategyLabels = {
        alphabet: 'A-Z',
        number: '#',
        'number-sequence': '# seq',
        phrase: 'Phrase',
        'word-by-word': 'Word by word',
    };
    const resultLabel = strategyLabels[payload.strategy] || 'Matched sign result';
    if (payload.strategy === 'number-sequence' && (payload.sequence || []).length) {
        dictionaryResultsMeta.textContent = `1 clip · ${resultLabel}`;
        renderCompiledNumberResult(query, payload, foundEntries);
        return;
    }

    resetDictionaryCompiledPlayback();
    dictionaryResultsMeta.textContent = `${foundEntries.length} · ${resultLabel}`;

    dictionaryResultsBody.innerHTML = foundEntries.map((entry) => {
        const primaryVideo = entry.videos[0];
        const extraSources = Math.max(entry.videos.length - 1, 0);
        const definition = entry.definition || 'No definition available.';

        return `
            <article class="dictionary-card">
                <div class="dictionary-card__media">
                    <video class="dictionary-card__video" controls preload="metadata" poster="${escapeAttribute(primaryVideo.poster || '')}">
                        <source src="${escapeAttribute(primaryVideo.src)}" type="video/mp4">
                    </video>
                </div>
                <div class="dictionary-card__copy">
                    <p class="dictionary-card__eyebrow">EN</p>
                    <h3 class="dictionary-card__word">${escapeHtml(entry.term || entry.display_term)}</h3>
                    <p class="dictionary-card__definition">${escapeHtml(definition)}</p>
                    <p class="dictionary-card__meta">
                        Src: ${escapeHtml(primaryVideo.provider || 'SignASL')}
                        ${extraSources ? ` · +${extraSources} src` : ''}
                    </p>
                    <a class="dictionary-card__link" href="${escapeAttribute(entry.page_url)}" target="_blank" rel="noreferrer">↗ Entry</a>
                </div>
            </article>
        `;
    }).join('');
}

function renderCompiledNumberResult(query, payload, foundEntries) {
    if (!dictionaryResultsBody) {
        return;
    }

    const definition = `The number ${query}.`;
    dictionaryResultsBody.innerHTML = `
        <article class="dictionary-card dictionary-card--compiled">
            <div class="dictionary-card__media">
                <video id="dictionary-compiled-video" class="dictionary-card__video dictionary-card__video--compiled" autoplay muted playsinline preload="metadata"></video>
            </div>
            <div class="dictionary-card__copy">
                <p class="dictionary-card__eyebrow">EN</p>
                <h3 class="dictionary-card__word">${escapeHtml(query)}</h3>
                <p class="dictionary-card__definition">${escapeHtml(definition)}</p>
                <p class="dictionary-card__meta">Digit-order playback.</p>
            </div>
        </article>
    `;

    dictionaryCompiledVideo = document.getElementById('dictionary-compiled-video');
    dictionaryCompiledSequence = payload.sequence || [];
    dictionaryCompiledIndex = 0;

    if (!dictionaryCompiledVideo || !dictionaryCompiledSequence.length) {
        return;
    }

    dictionaryCompiledVideo.addEventListener('ended', playNextDictionaryClip);
    loadDictionaryCompiledClip(0);
}

function resetDictionaryCompiledPlayback() {
    if (dictionaryCompiledVideo) {
        dictionaryCompiledVideo.pause();
        dictionaryCompiledVideo.removeAttribute('src');
        dictionaryCompiledVideo.load();
    }

    dictionaryCompiledVideo = null;
    dictionaryCompiledSequence = [];
    dictionaryCompiledIndex = 0;
}

function loadDictionaryCompiledClip(index) {
    if (!dictionaryCompiledVideo || !dictionaryCompiledSequence.length) {
        return;
    }

    const clip = dictionaryCompiledSequence[index];
    if (!clip) {
        return;
    }

    dictionaryCompiledIndex = index;
    dictionaryCompiledVideo.poster = clip.poster || '';
    dictionaryCompiledVideo.src = clip.src;
    dictionaryCompiledVideo.load();

    const playPromise = dictionaryCompiledVideo.play();
    if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => {
            // Ignore autoplay failures caused by browser policy.
        });
    }
}

function playNextDictionaryClip() {
    if (!dictionaryCompiledSequence.length) {
        return;
    }

    const nextIndex = (dictionaryCompiledIndex + 1) % dictionaryCompiledSequence.length;
    loadDictionaryCompiledClip(nextIndex);
}

async function runDictionarySearch(query) {
    if (!dictionaryLookupUrl) {
        return;
    }

    const trimmedQuery = sanitizeDictionaryQuery(query);
    if (!trimmedQuery) {
        renderDictionaryEmptyState();
        return;
    }

    if (dictionaryInput) {
        dictionaryInput.value = trimmedQuery;
    }

    if (dictionaryController) {
        dictionaryController.abort();
    }

    dictionaryController = new AbortController();
    renderDictionaryLoadingState();

    try {
        const response = await fetch(`${dictionaryLookupUrl}?text=${encodeURIComponent(trimmedQuery)}`, {
            signal: dictionaryController.signal,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        });

        if (!response.ok) {
            throw new Error('Dictionary lookup failed');
        }

        const payload = await response.json();
        renderDictionaryResults(trimmedQuery, payload);
        
        // Reload history after search
        if (dictionaryHistorySection) {
            void loadSearchHistory();
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            return;
        }

        renderDictionaryErrorState();
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeAttribute(value) {
    return escapeHtml(value);
}

async function loadSearchHistory() {
    if (!dictionaryHistoryUrl || !dictionaryHistorySection) {
        return;
    }

    try {
        const response = await fetch(dictionaryHistoryUrl, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        });

        if (!response.ok) {
            return;
        }

        const data = await response.json();
        renderSearchHistory(data.history || []);
    } catch (error) {
        // Silently fail - history is not critical
    }
}

function renderSearchHistory(history) {
    if (!dictionaryHistoryBody) {
        return;
    }

    if (!history.length) {
        dictionaryHistoryBody.innerHTML = `
            <div class="dictionary-empty-state">No search history yet.</div>
        `;
        return;
    }

    dictionaryHistoryBody.innerHTML = `
        <div class="dictionary-history__list">
            ${history.map((term) => `
                <button class="dictionary-history__item" data-search-term="${escapeAttribute(term)}">
                    ${escapeHtml(term)}
                </button>
            `).join('')}
        </div>
    `;

    // Add click handlers to history items
    const historyItems = dictionaryHistoryBody.querySelectorAll('.dictionary-history__item');
    historyItems.forEach((item) => {
        item.addEventListener('click', () => {
            const searchTerm = item.dataset.searchTerm;
            if (searchTerm) {
                void runDictionarySearch(searchTerm);
            }
        });
    });
}

async function clearSearchHistory() {
    if (!dictionaryClearHistoryUrl) {
        return;
    }

    try {
        const response = await fetch(dictionaryClearHistoryUrl, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(),
            },
        });

        if (response.ok) {
            renderSearchHistory([]);
        }
    } catch (error) {
        // Silently fail
    }
}

function getCsrfToken() {
    const cookieValue = document.cookie
        .split('; ')
        .find((row) => row.startsWith('csrftoken='));
    return cookieValue ? cookieValue.split('=')[1] : '';
}

if (dictionaryForm && dictionaryInput) {
    dictionaryInput.addEventListener('keydown', (event) => {
        if (event.key === ' ') {
            event.preventDefault();
        }
    });

    dictionaryInput.addEventListener('input', () => {
        const sanitizedValue = sanitizeDictionaryQuery(dictionaryInput.value);
        if (dictionaryInput.value !== sanitizedValue) {
            dictionaryInput.value = sanitizedValue;
        }
    });

    dictionaryInput.addEventListener('paste', (event) => {
        const pastedText = event.clipboardData ? event.clipboardData.getData('text') : '';
        const sanitizedValue = sanitizeDictionaryQuery(pastedText);
        if (!sanitizedValue) {
            event.preventDefault();
            return;
        }

        event.preventDefault();
        dictionaryInput.value = sanitizedValue;
    });

    dictionaryForm.addEventListener('submit', (event) => {
        event.preventDefault();
        void runDictionarySearch(dictionaryInput.value);
    });
}

if (clearHistoryBtn) {
    clearHistoryBtn.addEventListener('click', () => {
        void clearSearchHistory();
    });
}

renderDictionaryEmptyState();

// Load search history on page load
if (dictionaryHistorySection) {
    void loadSearchHistory();
}