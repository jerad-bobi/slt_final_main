const scoreFilterSelect = document.getElementById('score-filter');
const profileHistoryList = document.getElementById('profile-history-list');
const profileFilterCaption = document.getElementById('profile-filter-caption');

const pluralizeScores = (count) => (count === 1 ? 'score' : 'scores');

const updateCaption = (label, count) => {
    if (!profileFilterCaption) {
        return;
    }

    profileFilterCaption.textContent = `Showing ${count} saved ${pluralizeScores(count)} sorted by ${label.toLowerCase()}.`;
};

const comparators = {
    newest: (left, right) => Number(right.dataset.dateAttempt) - Number(left.dataset.dateAttempt)
        || Number(right.dataset.attemptNumber) - Number(left.dataset.attemptNumber),
    oldest: (left, right) => Number(left.dataset.dateAttempt) - Number(right.dataset.dateAttempt)
        || Number(left.dataset.attemptNumber) - Number(right.dataset.attemptNumber),
    highest: (left, right) => Number(right.dataset.score) - Number(left.dataset.score)
        || Number(right.dataset.dateAttempt) - Number(left.dataset.dateAttempt)
        || Number(right.dataset.attemptNumber) - Number(left.dataset.attemptNumber),
    lowest: (left, right) => Number(left.dataset.score) - Number(right.dataset.score)
        || Number(right.dataset.dateAttempt) - Number(left.dataset.dateAttempt)
        || Number(right.dataset.attemptNumber) - Number(left.dataset.attemptNumber),
};

const applyScoreSort = () => {
    if (!scoreFilterSelect || !profileHistoryList) {
        return;
    }

    const items = Array.from(profileHistoryList.querySelectorAll('.profile-history-item'));
    const comparator = comparators[scoreFilterSelect.value] || comparators.newest;
    items.sort(comparator);

    for (const item of items) {
        profileHistoryList.appendChild(item);
    }

    const selectedLabel = scoreFilterSelect.options[scoreFilterSelect.selectedIndex]?.text || 'Newest first';
    updateCaption(selectedLabel, items.length);
};

if (scoreFilterSelect && profileHistoryList) {
    scoreFilterSelect.addEventListener('change', applyScoreSort);
    applyScoreSort();
}
