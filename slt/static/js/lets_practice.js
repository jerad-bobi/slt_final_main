const translatorShell = document.querySelector('.translator-shell');
const swapButton = document.getElementById('swap-translator');
const modeLabel = document.getElementById('mode-label');
const sourceTitle = document.getElementById('source-title');
const sourceHint = document.getElementById('source-hint');
const targetTitle = document.getElementById('target-title');
const targetHint = document.getElementById('target-hint');
const textInput = document.getElementById('practice-text-input');
const signPreview = document.getElementById('sign-preview');
const cameraPreview = document.getElementById('camera-preview');
const cameraOverlay = document.getElementById('camera-overlay');
const cameraStatus = document.getElementById('camera-status');
const restartCameraButton = document.getElementById('restart-camera');
const lookupUrl = translatorShell ? translatorShell.dataset.lookupUrl : '';
const overlayContext = cameraOverlay ? cameraOverlay.getContext('2d') : null;

let lookupTimeoutId = null;
let activeLookupController = null;
let compiledVideo = null;
let compiledSequence = [];
let compiledIndex = 0;
let cameraStream = null;
let cameraRequestId = 0;
let handTracker = null;
let handTrackerReady = false;
let handTrackingFrameId = 0;
let handTrackingBusy = false;

const modes = {
    'text-to-sign': {
        label: 'Text → Sign',
        sourceTitle: 'Text',
        sourceHint: 'Word / phrase / sentence',
        targetTitle: 'Sign',
        targetHint: 'Preview',
        activeBlocks: ['text-to-sign-source', 'text-to-sign-target'],
    },
    'sign-to-text': {
        label: 'Sign → Text',
        sourceTitle: 'Cam',
        sourceHint: 'Camera / gesture',
        targetTitle: 'Text',
        targetHint: 'Result',
        activeBlocks: ['sign-to-text-source', 'sign-to-text-target'],
    },
};

function setMode(nextMode) {
    const config = modes[nextMode];
    if (!config || !translatorShell) {
        return;
    }

    translatorShell.dataset.mode = nextMode;
    modeLabel.textContent = config.label;
    sourceTitle.textContent = config.sourceTitle;
    sourceHint.textContent = config.sourceHint;
    targetTitle.textContent = config.targetTitle;
    targetHint.textContent = config.targetHint;

    document.querySelectorAll('[data-mode-block]').forEach((block) => {
        const isActive = config.activeBlocks.includes(block.dataset.modeBlock);
        block.classList.toggle('mode-block--active', isActive);
    });

    if (nextMode === 'sign-to-text') {
        void startCameraPreview();
    } else {
        stopCameraPreview();
    }
}

function updateSignPreview() {
    if (!signPreview || !textInput) {
        return;
    }

    const inputValue = textInput.value.trim();

    if (!inputValue.length) {
        renderEmptyState();
        return;
    }

    renderLoadingState();

    if (lookupTimeoutId) {
        window.clearTimeout(lookupTimeoutId);
    }

    lookupTimeoutId = window.setTimeout(() => {
        fetchSignTranslations(inputValue);
    }, 250);
}

async function fetchSignTranslations(text) {
    if (!lookupUrl || !signPreview) {
        return;
    }

    if (activeLookupController) {
        activeLookupController.abort();
    }

    activeLookupController = new AbortController();

    try {
        const response = await fetch(`${lookupUrl}?text=${encodeURIComponent(text)}`, {
            signal: activeLookupController.signal,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        });

        if (!response.ok) {
            throw new Error('Lookup failed');
        }

        const payload = await response.json();
        renderLookupResults(payload);
    } catch (error) {
        if (error.name === 'AbortError') {
            return;
        }

        renderEmptyState();
    }
}

function renderLookupResults(payload) {
    if (!signPreview) {
        return;
    }

    const sequence = payload.sequence || [];

    if (!sequence.length) {
        renderEmptyState();
        return;
    }

    signPreview.innerHTML = `
        <div class="sign-result-list sign-result-list--compiled">
            <article class="sign-result-card sign-result-card--compiled">
                <video id="compiled-sign-video" class="sign-result-video sign-result-video--compiled" autoplay muted playsinline preload="metadata"></video>
            </article>
        </div>
    `;

    compiledVideo = document.getElementById('compiled-sign-video');
    compiledSequence = sequence;
    compiledIndex = 0;

    if (!compiledVideo) {
        return;
    }

    compiledVideo.addEventListener('ended', playNextClip);
    loadCompiledClip(0);
}

function renderEmptyState() {
    if (!signPreview) {
        return;
    }

    resetCompiledPlayback();

    signPreview.innerHTML = '<div class="sign-preview__empty-state" aria-hidden="true"></div>';
}

function renderLoadingState() {
    if (!signPreview) {
        return;
    }

    resetCompiledPlayback();

    signPreview.innerHTML = `
        <div class="sign-result-list sign-result-list--loading" aria-hidden="true">
            <div class="sign-result-card sign-result-card--loading"></div>
        </div>
    `;
}

function resetCompiledPlayback() {
    if (compiledVideo) {
        compiledVideo.pause();
        compiledVideo.removeAttribute('src');
        compiledVideo.load();
    }

    compiledVideo = null;
    compiledSequence = [];
    compiledIndex = 0;
}

async function startCameraPreview() {
    if (!cameraPreview || !cameraStatus) {
        return;
    }

    const requestId = ++cameraRequestId;

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        cameraStatus.textContent = 'No camera support.';
        cameraStatus.classList.add('camera-status--visible');
        return;
    }

    if (!window.isSecureContext) {
        cameraStatus.textContent = 'Use HTTPS / localhost.';
        cameraStatus.classList.add('camera-status--visible');
        return;
    }

    cameraStatus.textContent = 'Opening camera...';
    cameraStatus.classList.add('camera-status--visible');

    try {
        stopCameraPreview();

        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'user',
                width: { ideal: 1280 },
                height: { ideal: 720 },
            },
            audio: false,
        });

        if (requestId !== cameraRequestId) {
            stream.getTracks().forEach((track) => track.stop());
            return;
        }

        cameraStream = stream;
        cameraPreview.srcObject = stream;

        const playPromise = cameraPreview.play();
        if (playPromise && typeof playPromise.catch === 'function') {
            playPromise.catch(() => {
                // Some browsers still defer playback until the stream is ready.
            });
        }

        syncCameraOverlaySize();
        await ensureHandTracker();
        startHandTrackingLoop();

        cameraStatus.textContent = '';
        cameraStatus.classList.remove('camera-status--visible');
    } catch (error) {
        cameraStatus.textContent = buildCameraErrorMessage(error);
        cameraStatus.classList.add('camera-status--visible');
    }
}

function stopCameraPreview() {
    stopHandTrackingLoop();

    if (cameraPreview) {
        cameraPreview.pause();
        cameraPreview.srcObject = null;
    }

    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
    }

    cameraStream = null;

    if (cameraStatus) {
        cameraStatus.textContent = 'Switch to Sign → Text.';
        cameraStatus.classList.add('camera-status--visible');
    }
}

async function ensureHandTracker() {
    if (handTrackerReady || typeof window.Hands !== 'function') {
        return;
    }

    handTracker = new window.Hands({
        locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`,
    });

    handTracker.setOptions({
        maxNumHands: 2,
        modelComplexity: 1,
        minDetectionConfidence: 0.6,
        minTrackingConfidence: 0.5,
    });

    handTracker.onResults(handleHandTrackingResults);
    handTrackerReady = true;
}

function startHandTrackingLoop() {
    if (!cameraPreview || !handTrackerReady || handTrackingFrameId) {
        return;
    }

    const processFrame = async () => {
        if (!cameraPreview || translatorShell?.dataset.mode !== 'sign-to-text') {
            handTrackingFrameId = 0;
            return;
        }

        if (cameraPreview.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && !handTrackingBusy) {
            handTrackingBusy = true;

            try {
                syncCameraOverlaySize();
                await handTracker.send({ image: cameraPreview });
            } catch (error) {
                clearCameraOverlay();
            } finally {
                handTrackingBusy = false;
            }
        }

        handTrackingFrameId = window.requestAnimationFrame(processFrame);
    };

    handTrackingFrameId = window.requestAnimationFrame(processFrame);
}

function stopHandTrackingLoop() {
    if (handTrackingFrameId) {
        window.cancelAnimationFrame(handTrackingFrameId);
        handTrackingFrameId = 0;
    }

    handTrackingBusy = false;
    clearCameraOverlay();
}

function syncCameraOverlaySize() {
    if (!cameraOverlay || !cameraPreview) {
        return;
    }

    const width = cameraPreview.videoWidth || cameraPreview.clientWidth;
    const height = cameraPreview.videoHeight || cameraPreview.clientHeight;

    if (!width || !height) {
        return;
    }

    if (cameraOverlay.width !== width) {
        cameraOverlay.width = width;
    }

    if (cameraOverlay.height !== height) {
        cameraOverlay.height = height;
    }
}

function clearCameraOverlay() {
    if (!cameraOverlay || !overlayContext) {
        return;
    }

    overlayContext.clearRect(0, 0, cameraOverlay.width, cameraOverlay.height);
}

function handleHandTrackingResults(results) {
    if (!overlayContext || !cameraOverlay) {
        return;
    }

    overlayContext.save();
    overlayContext.clearRect(0, 0, cameraOverlay.width, cameraOverlay.height);

    const landmarkSets = results.multiHandLandmarks || [];
    for (const landmarks of landmarkSets) {
        window.drawConnectors(overlayContext, landmarks, window.HAND_CONNECTIONS, {
            color: '#ffc857',
            lineWidth: 3,
        });
        window.drawLandmarks(overlayContext, landmarks, {
            color: '#fff8e7',
            fillColor: '#f96f5d',
            lineWidth: 1,
            radius: 4,
        });
    }

    overlayContext.restore();
}

function buildCameraErrorMessage(error) {
    if (!error || !error.name) {
        return 'Unable to access the camera.';
    }

    if (error.name === 'NotAllowedError') {
        return 'Camera denied.';
    }

    if (error.name === 'NotFoundError') {
        return 'No camera found.';
    }

    if (error.name === 'NotReadableError') {
        return 'Camera busy.';
    }

    return 'Camera unavailable.';
}

function loadCompiledClip(index) {
    if (!compiledVideo || !compiledSequence.length) {
        return;
    }

    const clip = compiledSequence[index];
    if (!clip) {
        return;
    }

    compiledIndex = index;
    compiledVideo.poster = clip.poster || '';
    compiledVideo.src = clip.src;
    compiledVideo.load();

    const playPromise = compiledVideo.play();
    if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(() => {
            // Ignore autoplay failures caused by browser policy.
        });
    }
}

function playNextClip() {
    if (!compiledSequence.length) {
        return;
    }

    const nextIndex = (compiledIndex + 1) % compiledSequence.length;
    loadCompiledClip(nextIndex);
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

if (swapButton && translatorShell) {
    swapButton.addEventListener('click', () => {
        const currentMode = translatorShell.dataset.mode;
        const nextMode = currentMode === 'text-to-sign' ? 'sign-to-text' : 'text-to-sign';
        setMode(nextMode);
    });
}

if (textInput) {
    textInput.addEventListener('input', updateSignPreview);
}

if (restartCameraButton) {
    restartCameraButton.addEventListener('click', () => {
        if (translatorShell && translatorShell.dataset.mode === 'sign-to-text') {
            void startCameraPreview();
        }
    });
}

window.addEventListener('beforeunload', stopCameraPreview);
window.addEventListener('resize', syncCameraOverlaySize);

setMode('text-to-sign');
renderEmptyState();