const brainLaunchButton = document.getElementById('brain-launch-quiz');
const brainQuizModal = document.getElementById('brain-quiz-modal');
const brainCloseButton = document.getElementById('brain-close-quiz');
const brainStartScreen = document.getElementById('brain-start-screen');
const brainQuizGame = document.getElementById('brain-quiz-game');
const brainEndScreen = document.getElementById('brain-end-screen');
const brainStartButton = document.getElementById('brain-start-quiz');
const brainRestartButton = document.getElementById('brain-restart-quiz');
const brainTimerFill = document.getElementById('brain-timer-fill');
const brainTimerLabel = document.getElementById('brain-timer-label');
const brainScore = document.getElementById('brain-score');
const brainAnswered = document.getElementById('brain-answered');
const brainSpeed = document.getElementById('brain-speed');
const brainQuestionPrompt = document.getElementById('brain-question-prompt');
const brainFeedback = document.getElementById('brain-feedback');
const brainVideoShell = document.getElementById('brain-video-shell');
const brainOptions = document.getElementById('brain-options');
const brainEndSummary = document.getElementById('brain-end-summary');

const brainQuizState = {
    active: false,
    timer: 100,
    score: 0,
    answered: 0,
    currentQuestion: null,
    lastTickAt: 0,
    animationFrameId: 0,
    loadingQuestion: false,
    locked: false,
    requestId: 0,
    timerPaused: true,
    scoreSaved: false,
    scoreSaveStatus: '',
};

const brainQuizApiUrl = brainQuizModal ? brainQuizModal.dataset.quizUrl || '' : '';
const brainQuizAttemptSaveUrl = brainQuizModal ? brainQuizModal.dataset.saveAttemptUrl || '' : '';

function openBrainQuizModal() {
    if (!brainQuizModal) {
        return;
    }

    brainQuizModal.classList.add('quiz-modal--visible');
    brainQuizModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('quiz-modal-open');
    showBrainStartScreen();
}

function closeBrainQuizModal() {
    if (!brainQuizModal) {
        return;
    }

    stopBrainQuiz();
    brainQuizModal.classList.remove('quiz-modal--visible');
    brainQuizModal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('quiz-modal-open');
}

function showBrainStartScreen() {
    if (!brainStartScreen || !brainQuizGame || !brainEndScreen) {
        return;
    }

    brainStartScreen.hidden = false;
    brainQuizGame.hidden = true;
    brainEndScreen.hidden = true;
}

function showBrainGameScreen() {
    if (!brainStartScreen || !brainQuizGame || !brainEndScreen) {
        return;
    }

    brainStartScreen.hidden = true;
    brainQuizGame.hidden = false;
    brainEndScreen.hidden = true;
}

function showBrainEndScreen() {
    if (!brainStartScreen || !brainQuizGame || !brainEndScreen || !brainEndSummary) {
        return;
    }

    brainStartScreen.hidden = true;
    brainQuizGame.hidden = true;
    brainEndScreen.hidden = false;
    const saveSuffix = brainQuizState.scoreSaveStatus ? ` ${brainQuizState.scoreSaveStatus}` : '';
    brainEndSummary.textContent = `You scored ${brainQuizState.score} and answered ${brainQuizState.answered} questions before the timer ran out.${saveSuffix}`;
}

function resetBrainQuizState() {
    brainQuizState.active = true;
    brainQuizState.timer = 100;
    brainQuizState.score = 0;
    brainQuizState.answered = 0;
    brainQuizState.currentQuestion = null;
    brainQuizState.lastTickAt = 0;
    brainQuizState.locked = false;
    brainQuizState.timerPaused = true;
    brainQuizState.scoreSaved = false;
    brainQuizState.scoreSaveStatus = '';
    renderBrainHud();
    renderBrainLoadingQuestion('Loading question...');
    renderBrainFeedback('Timer will start when the video begins playing.', 'idle');
}

function stopBrainQuiz() {
    brainQuizState.active = false;
    brainQuizState.currentQuestion = null;
    brainQuizState.locked = false;
    brainQuizState.requestId += 1;
    brainQuizState.timerPaused = true;

    if (brainQuizState.animationFrameId) {
        window.cancelAnimationFrame(brainQuizState.animationFrameId);
        brainQuizState.animationFrameId = 0;
    }
}

function finishBrainQuiz() {
    stopBrainQuiz();
    showBrainEndScreen();
    void saveBrainQuizAttempt();
}

async function saveBrainQuizAttempt() {
    if (!brainQuizAttemptSaveUrl || brainQuizState.scoreSaved) {
        return;
    }

    brainQuizState.scoreSaved = true;

    try {
        const response = await fetch(brainQuizAttemptSaveUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(),
            },
            body: JSON.stringify({
                score: brainQuizState.score,
            }),
        });

        if (response.status === 401) {
            brainQuizState.scoreSaveStatus = ' Login to store your score history.';
            showBrainEndScreen();
            return;
        }

        if (!response.ok) {
            throw new Error('Attempt save failed');
        }

        const payload = await response.json();
        brainQuizState.scoreSaveStatus = ` Saved as attempt ${payload.attempt_number} for ${payload.username}.`;
        showBrainEndScreen();
    } catch (error) {
        brainQuizState.scoreSaved = false;
        brainQuizState.scoreSaveStatus = ' Score could not be saved.';
        showBrainEndScreen();
    }
}

function startBrainQuiz() {
    resetBrainQuizState();
    showBrainGameScreen();
    void loadBrainQuestion();
    brainQuizState.animationFrameId = window.requestAnimationFrame(stepBrainTimer);
}

function getBrainDrainRate() {
    return 3.6 + Math.min(brainQuizState.answered * 0.18, 7.6);
}

function renderBrainHud() {
    if (!brainTimerFill || !brainTimerLabel || !brainScore || !brainAnswered || !brainSpeed) {
        return;
    }

    const timerValue = Math.max(0, Math.min(100, brainQuizState.timer));
    const speedValue = getBrainDrainRate() / 3.6;

    brainTimerFill.style.width = `${timerValue}%`;
    brainTimerLabel.textContent = brainQuizState.timerPaused ? `Paused · ${Math.round(timerValue)}%` : `${Math.round(timerValue)}%`;
    brainScore.textContent = String(brainQuizState.score);
    brainAnswered.textContent = String(brainQuizState.answered);
    brainSpeed.textContent = `${speedValue.toFixed(1)}x`;

    brainTimerFill.classList.toggle('quiz-timer__fill--danger', timerValue <= 30);
}

function stepBrainTimer(timestamp) {
    if (!brainQuizState.active) {
        return;
    }

    if (!brainQuizState.lastTickAt) {
        brainQuizState.lastTickAt = timestamp;
    }

    const deltaSeconds = (timestamp - brainQuizState.lastTickAt) / 1000;
    brainQuizState.lastTickAt = timestamp;

    if (!brainQuizState.timerPaused) {
        brainQuizState.timer = Math.max(0, brainQuizState.timer - (deltaSeconds * getBrainDrainRate()));
    }

    renderBrainHud();

    if (brainQuizState.timer <= 0) {
        finishBrainQuiz();
        return;
    }

    brainQuizState.animationFrameId = window.requestAnimationFrame(stepBrainTimer);
}

function renderBrainLoadingQuestion(message) {
    if (!brainVideoShell || !brainOptions) {
        return;
    }

    brainVideoShell.innerHTML = `<div class="quiz-video-shell__loading">${escapeBrainHtml(message)}</div>`;
    brainOptions.innerHTML = '';
}

function renderBrainFeedback(message, tone) {
    if (!brainFeedback) {
        return;
    }

    brainFeedback.textContent = message;
    brainFeedback.dataset.tone = tone;
}

async function loadBrainQuestion() {
    if (brainQuizState.loadingQuestion || !brainQuizState.active || !brainQuizApiUrl) {
        return;
    }

    brainQuizState.loadingQuestion = true;
    brainQuizState.locked = true;
    brainQuizState.timerPaused = true;
    brainQuizState.lastTickAt = 0;
    renderBrainHud();
    const requestId = ++brainQuizState.requestId;
    renderBrainLoadingQuestion('Loading question...');

    try {
        const response = await fetch(brainQuizApiUrl, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        });

        if (!response.ok) {
            throw new Error('Quiz question request failed');
        }

        const payload = await response.json();
        if (!brainQuizState.active || requestId !== brainQuizState.requestId) {
            return;
        }

        brainQuizState.currentQuestion = payload;
        brainQuizState.locked = false;
        renderBrainQuestion(payload);
        renderBrainFeedback('Timer will start when the video begins playing.', 'idle');
    } catch (error) {
        if (!brainQuizState.active || requestId !== brainQuizState.requestId) {
            return;
        }

        renderBrainFeedback('Question unavailable. Trying again...', 'warning');
        window.setTimeout(() => {
            if (brainQuizState.active) {
                void loadBrainQuestion();
            }
        }, 900);
    } finally {
        brainQuizState.loadingQuestion = false;
    }
}

function renderBrainQuestion(question) {
    if (!brainVideoShell || !brainOptions || !brainQuestionPrompt) {
        return;
    }

    brainQuestionPrompt.textContent = question.prompt || 'What does this sign mean?';

    brainVideoShell.innerHTML = `
        <div class="quiz-video-row">
            <video id="brain-quiz-video" class="quiz-video" controls autoplay muted playsinline preload="auto" poster="${escapeBrainAttribute(question.video.poster || '')}">
                <source src="${escapeBrainAttribute(question.video.src || '')}" type="video/mp4">
            </video>
            <aside class="quiz-debug-answer" aria-label="Temporary answer hint">
                <span class="quiz-debug-answer__label">Temporary answer</span>
                <strong class="quiz-debug-answer__value">${escapeBrainHtml(question.correct_label || '')}</strong>
            </aside>
        </div>
        <a class="quiz-source-link" href="${escapeBrainAttribute(question.video.page_url || '#')}" target="_blank" rel="noreferrer">Open source entry</a>
    `;

    setupBrainVideoTimerGate();

    brainOptions.innerHTML = (question.choices || []).map((choice) => `
        <button class="quiz-option" type="button" data-value="${escapeBrainAttribute(choice.value)}">${escapeBrainHtml(choice.label)}</button>
    `).join('');

    brainOptions.querySelectorAll('.quiz-option').forEach((button) => {
        button.addEventListener('click', () => {
            handleBrainAnswer(button.dataset.value || '');
        });
    });
}

function setupBrainVideoTimerGate() {
    const video = document.getElementById('brain-quiz-video');
    if (!video) {
        return;
    }

    let started = false;
    let playbackStarted = false;
    let fullyLoaded = false;

    const isVideoFullyBuffered = () => {
        if (video.readyState >= HTMLMediaElement.HAVE_ENOUGH_DATA) {
            return true;
        }

        if (!Number.isFinite(video.duration) || video.duration <= 0 || video.buffered.length === 0) {
            return false;
        }

        const bufferedEnd = video.buffered.end(video.buffered.length - 1);
        return bufferedEnd >= video.duration - 0.15;
    };

    const startTimerIfReady = () => {
        if (started || !brainQuizState.active || !playbackStarted || !fullyLoaded) {
            return;
        }

        started = true;
        brainQuizState.timerPaused = false;
        brainQuizState.lastTickAt = 0;
        renderBrainHud();
        renderBrainFeedback('Choose the matching answer.', 'idle');
    };

    const markVideoLoaded = () => {
        if (fullyLoaded || !brainQuizState.active) {
            return;
        }

        if (!isVideoFullyBuffered()) {
            return;
        }

        fullyLoaded = true;
        renderBrainFeedback('Video loaded. Timer starts when playback begins.', 'idle');
        startTimerIfReady();
    };

    const handlePlaybackStarted = () => {
        if (!brainQuizState.active) {
            return;
        }

        playbackStarted = true;
        startTimerIfReady();
    };

    const requestPlayback = () => {
        const playPromise = video.play();
        if (playPromise && typeof playPromise.catch === 'function') {
            playPromise.catch(() => {
                renderBrainFeedback('Video loaded. Press play to start the timer.', 'warning');
            });
        }
    };

    video.addEventListener('playing', handlePlaybackStarted);
    video.addEventListener('canplaythrough', () => {
        markVideoLoaded();
        requestPlayback();
    }, { once: true });
    video.addEventListener('progress', markVideoLoaded);
    video.addEventListener('loadeddata', markVideoLoaded);
    video.addEventListener('suspend', markVideoLoaded);
    video.addEventListener('error', () => {
        renderBrainFeedback('Video failed to load. Fetching another question...', 'warning');
        if (brainQuizState.active) {
            window.setTimeout(() => {
                if (brainQuizState.active) {
                    void loadBrainQuestion();
                }
            }, 400);
        }
    }, { once: true });

    if (isVideoFullyBuffered()) {
        markVideoLoaded();
        requestPlayback();
    }
}

function handleBrainAnswer(selectedValue) {
    if (!brainQuizState.currentQuestion || brainQuizState.locked || !brainOptions) {
        return;
    }

    brainQuizState.locked = true;
    brainQuizState.timerPaused = true;
    brainQuizState.answered += 1;

    const correctValue = brainQuizState.currentQuestion.correct_answer;
    const isCorrect = selectedValue === correctValue;

    if (isCorrect) {
        brainQuizState.score += 1;
        brainQuizState.timer = Math.min(100, brainQuizState.timer + 14);
        renderBrainFeedback(`Correct. ${brainQuizState.currentQuestion.correct_label} refilled the timer.`, 'success');
    } else {
        brainQuizState.timer = Math.max(0, brainQuizState.timer - 10);
        renderBrainFeedback(`Incorrect. The sign was ${brainQuizState.currentQuestion.correct_label}.`, 'danger');
    }

    renderBrainHud();

    brainOptions.querySelectorAll('.quiz-option').forEach((button) => {
        const buttonValue = button.dataset.value || '';
        button.disabled = true;
        if (buttonValue === correctValue) {
            button.classList.add('quiz-option--correct');
        } else if (buttonValue === selectedValue && !isCorrect) {
            button.classList.add('quiz-option--wrong');
        }
    });

    window.setTimeout(() => {
        if (!brainQuizState.active || brainQuizState.timer <= 0) {
            finishBrainQuiz();
            return;
        }

        void loadBrainQuestion();
    }, 700);
}

function escapeBrainHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeBrainAttribute(value) {
    return escapeBrainHtml(value);
}

function getCsrfToken() {
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (csrfInput instanceof HTMLInputElement && csrfInput.value) {
        return csrfInput.value;
    }

    const csrfCookie = document.cookie
        .split('; ')
        .find((cookie) => cookie.startsWith('csrftoken='));

    return csrfCookie ? decodeURIComponent(csrfCookie.split('=')[1]) : '';
}

if (brainLaunchButton) {
    brainLaunchButton.addEventListener('click', openBrainQuizModal);
}

if (brainCloseButton) {
    brainCloseButton.addEventListener('click', closeBrainQuizModal);
}

if (brainQuizModal) {
    brainQuizModal.addEventListener('click', (event) => {
        const target = event.target;
        if (target instanceof HTMLElement && target.dataset.closeQuiz === 'true') {
            closeBrainQuizModal();
        }
    });
}

if (brainStartButton) {
    brainStartButton.addEventListener('click', startBrainQuiz);
}

if (brainRestartButton) {
    brainRestartButton.addEventListener('click', startBrainQuiz);
}

window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && brainQuizModal && brainQuizModal.classList.contains('quiz-modal--visible')) {
        closeBrainQuizModal();
    }
});