(function () {
    const lesson = document.querySelector('.syllabus-lesson');
    if (!lesson) {
        return;
    }

    const lookupUrl = lesson.dataset.lookupUrl || '';
    const predictUrl = lesson.dataset.predictUrl || '';
    const initialTerm = lesson.dataset.term || 'A';
    const videoShell = document.getElementById('syllabus-video-shell');
    const cameraPreview = document.getElementById('syllabus-camera-preview');
    const cameraOverlay = document.getElementById('syllabus-camera-overlay');
    const cameraStatus = document.getElementById('syllabus-camera-status');
    const detectionOutput = document.getElementById('syllabus-detection-output');
    const restartCameraButton = document.getElementById('syllabus-restart-camera');
    const proceedButton = document.getElementById('syllabus-proceed-button');
    const lessonTitle = document.getElementById('syllabus-lesson-title');
    const referenceTitle = document.getElementById('syllabus-reference-title');
    const cameraPrompt = document.getElementById('syllabus-camera-prompt');
    const instructionList = document.getElementById('syllabus-instruction-list');
    const overlayContext = cameraOverlay ? cameraOverlay.getContext('2d') : null;
    const termsDataNode = document.getElementById('syllabus-terms-data');

    const syllabusTerms = termsDataNode ? JSON.parse(termsDataNode.textContent) : [initialTerm];

    let cameraStream = null;
    let handTracker = null;
    let handTrackerReady = false;
    let handTrackingFrameId = 0;
    let handTrackingBusy = false;
    let signPredictionIntervalId = 0;
    let signPredictionBusy = false;
    let currentHandLandmarks = [];
    let hasMatchedCorrectSign = false;
    let lastAudibleOutcome = '';
    let correctHoldStartTime = 0;
    let lastHoldCountdownValue = 0;
    let currentTermIndex = Math.max(0, syllabusTerms.indexOf(initialTerm));

    const correctHoldDurationMs = 3000;
    const termInstructions = {
        A: [
            'Close your fingers into a gentle fist.',
            'Keep your thumb resting along the side of the fist.',
            'Hold the hand shape still and clear for the camera.',
        ],
        B: [
            'Raise four fingers straight up and keep them together.',
            'Fold your thumb across the palm beneath the fingers.',
            'Keep the palm open and facing the camera clearly.',
        ],
        C: [
            'Curve your fingers and thumb into the shape of a letter C.',
            'Leave a clear open space in the middle of the hand.',
            'Avoid closing the shape too tightly while holding steady.',
        ],
        D: [
            'Touch the tip of your thumb to the tips of the middle, ring, and pinky fingers.',
            'Keep the index finger pointing straight up.',
            'Show the upright finger clearly to the camera.',
        ],
        E: [
            'Curl all four fingers inward toward the palm.',
            'Tuck the thumb lightly across the front of the fingertips.',
            'Keep the hand compact without making a tight fist.',
        ],
        F: [
            'Touch the thumb tip to the index fingertip to make a circle.',
            'Raise the middle, ring, and pinky fingers upward.',
            'Keep the three raised fingers separated enough to be visible.',
        ],
        G: [
            'Point the index finger sideways.',
            'Extend the thumb parallel to the index finger.',
            'Keep the other fingers folded while showing the sideways hand shape.',
        ],
        H: [
            'Extend the index and middle fingers straight together sideways.',
            'Fold the ring finger and pinky inward.',
            'Keep the thumb supporting the folded fingers.',
        ],
        I: [
            'Fold the thumb, index, middle, and ring fingers inward.',
            'Raise only the pinky finger.',
            'Keep the pinky straight and easy to see.',
        ],
        J: [
            'Start with the hand shape for I.',
            'Use the pinky to draw a small J in the air.',
            'Move slowly enough for the motion to be visible.',
        ],
        K: [
            'Raise the index and middle fingers into a V shape.',
            'Place the thumb against the base of the middle finger.',
            'Keep the two raised fingers angled upward and apart.',
        ],
        L: [
            'Raise the index finger upward.',
            'Extend the thumb outward to form an L shape.',
            'Fold the remaining fingers into the palm.',
        ],
        M: [
            'Fold the thumb under the index, middle, and ring fingers.',
            'Let the pinky rest outside the folded fingers.',
            'Keep the three fingers clearly covering the thumb.',
        ],
        N: [
            'Fold the thumb under the index and middle fingers.',
            'Let the ring finger and pinky rest outside the thumb.',
            'Show that only two fingers cover the thumb.',
        ],
        O: [
            'Curve all fingers and thumb together into a round O shape.',
            'Touch the fingertips and thumb lightly.',
            'Keep the circle visible from the camera angle.',
        ],
        P: [
            'Start from a K hand shape.',
            'Angle the hand downward so the fingers point diagonally.',
            'Keep the thumb touching the middle finger while holding the tilt.',
        ],
        Q: [
            'Start from a G hand shape.',
            'Angle the hand downward so the index finger points diagonally.',
            'Keep the thumb extended beside the index finger.',
        ],
        R: [
            'Cross the middle finger over the index finger.',
            'Fold the thumb, ring finger, and pinky inward.',
            'Show the crossed fingers clearly to the camera.',
        ],
        S: [
            'Make a fist with all fingers folded in.',
            'Place the thumb across the front of the fingers.',
            'Keep the hand compact and steady.',
        ],
        T: [
            'Make a fist with the fingers folded inward.',
            'Tuck the thumb between the index and middle fingers.',
            'Show the thumb placement clearly without hiding the hand.',
        ],
        U: [
            'Raise the index and middle fingers straight up together.',
            'Keep them close side by side without crossing.',
            'Fold the thumb, ring finger, and pinky inward.',
        ],
        V: [
            'Raise the index and middle fingers into a V shape.',
            'Keep the other fingers folded into the palm.',
            'Spread the two raised fingers clearly apart.',
        ],
        W: [
            'Raise the index, middle, and ring fingers upward.',
            'Spread the three fingers slightly apart.',
            'Fold the thumb and pinky inward.',
        ],
        X: [
            'Make a fist and raise the index finger in a hooked shape.',
            'Keep the bent index finger visible from the side.',
            'Fold the remaining fingers in tightly.',
        ],
        Y: [
            'Extend the thumb and pinky outward.',
            'Fold the index, middle, and ring fingers inward.',
            'Keep the hand open enough to show both extended points.',
        ],
        Z: [
            'Raise the index finger while the other fingers stay folded.',
            'Draw the letter Z in the air with the index finger.',
            'Make the zigzag motion large enough for the camera to see.',
        ],
        0: [
            'Curve the fingers and thumb together into a neat closed oval.',
            'Keep the shape round and balanced like the number zero.',
            'Hold the hand still so the oval remains visible.',
        ],
        1: [
            'Raise the index finger straight up.',
            'Fold the thumb and remaining fingers into the palm.',
            'Keep the single raised finger centered for the camera.',
        ],
        2: [
            'Raise the index and middle fingers upward.',
            'Keep them separated slightly like the number two.',
            'Fold the remaining fingers inward.',
        ],
        3: [
            'Extend the thumb, index finger, and middle finger.',
            'Fold the ring finger and pinky inward.',
            'Keep the three visible digits clearly spread.',
        ],
        4: [
            'Raise four fingers upward together.',
            'Fold the thumb across the palm.',
            'Keep the four raised fingers straight and visible.',
        ],
        5: [
            'Open the whole hand wide.',
            'Spread all five digits naturally.',
            'Keep the palm facing forward and steady.',
        ],
        6: [
            'Touch the thumb to the pinky fingertip.',
            'Raise the index, middle, and ring fingers upward.',
            'Keep the three raised fingers clear while the circle stays visible.',
        ],
        7: [
            'Touch the thumb to the ring fingertip.',
            'Raise the index, middle, and pinky fingers upward.',
            'Hold the finger contact clearly for the camera.',
        ],
        8: [
            'Touch the thumb to the middle fingertip.',
            'Raise the index, ring, and pinky fingers upward.',
            'Keep the hand open enough to show the contact point.',
        ],
        9: [
            'Touch the thumb to the index fingertip to form a circle.',
            'Raise the middle, ring, and pinky fingers upward.',
            'Keep the circle and the raised fingers visible together.',
        ],
    };

    function getCurrentTerm() {
        return syllabusTerms[currentTermIndex] || initialTerm;
    }

    function getInstructionsForTerm(term) {
        return termInstructions[term] || [
            'Match the reference hand shape as closely as possible.',
            'Keep your fingers visible and the hand centered in the frame.',
            'Hold the sign steady until the camera confirms it.',
        ];
    }

    function updateInstructionList() {
        if (!instructionList) {
            return;
        }

        const currentTerm = getCurrentTerm();
        const instructions = getInstructionsForTerm(currentTerm);

        instructionList.innerHTML = instructions
            .map(function (instruction) {
                return '<li>' + instruction + '</li>';
            })
            .join('');
    }

    function updateLessonLabels() {
        const currentTerm = getCurrentTerm();

        if (lessonTitle) {
            lessonTitle.textContent = 'Sign Lesson: ' + currentTerm;
        }

        if (referenceTitle) {
            referenceTitle.textContent = 'How to sign ' + currentTerm;
        }

        if (cameraPrompt) {
            cameraPrompt.textContent = 'Imitate the sign ' + currentTerm;
        }

        updateInstructionList();
    }

    async function loadReferenceVideo() {
        if (!lookupUrl || !videoShell) {
            return;
        }

        const currentTerm = getCurrentTerm();
        videoShell.innerHTML = '<div class="syllabus-video-shell__loading">Loading sign video...</div>';

        try {
            const response = await fetch(lookupUrl + '?text=' + encodeURIComponent(currentTerm), {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (!response.ok) {
                throw new Error('Lookup failed');
            }

            const payload = await response.json();
            const sequence = Array.isArray(payload.sequence) ? payload.sequence : [];
            const firstVideo = sequence[0];

            if (!firstVideo || !firstVideo.src) {
                videoShell.innerHTML = '<div class="syllabus-video-shell__loading">No SignASL video found for this lesson yet.</div>';
                return;
            }

            videoShell.innerHTML = '<video class="syllabus-reference-video" controls autoplay muted loop playsinline preload="metadata"></video>';
            const video = videoShell.querySelector('video');
            video.src = firstVideo.src;
            if (firstVideo.poster) {
                video.poster = firstVideo.poster;
            }
        } catch (error) {
            videoShell.innerHTML = '<div class="syllabus-video-shell__loading">Unable to load the SignASL reference video.</div>';
        }
    }

    function renderDetectionMessage(message, tone) {
        if (!detectionOutput) {
            return;
        }

        detectionOutput.textContent = message;
        detectionOutput.dataset.tone = tone || 'idle';
    }

    function revealProceedButton() {
        if (proceedButton) {
            proceedButton.hidden = false;
        }
    }

    function hideProceedButton() {
        if (proceedButton) {
            proceedButton.hidden = true;
        }
    }

    function resetCorrectHold() {
        correctHoldStartTime = 0;
        lastHoldCountdownValue = 0;
    }

    function playSuccessPing() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            return;
        }

        const audioContext = new AudioContextClass();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        const now = audioContext.currentTime;

        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(880, now);
        oscillator.frequency.exponentialRampToValueAtTime(1320, now + 0.08);

        gainNode.gain.setValueAtTime(0.0001, now);
        gainNode.gain.exponentialRampToValueAtTime(0.12, now + 0.02);
        gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.start(now);
        oscillator.stop(now + 0.24);
        oscillator.addEventListener('ended', function () {
            if (typeof audioContext.close === 'function') {
                void audioContext.close();
            }
        });
    }

    function playIncorrectBuzz() {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            return;
        }

        const audioContext = new AudioContextClass();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        const now = audioContext.currentTime;

        oscillator.type = 'square';
        oscillator.frequency.setValueAtTime(320, now);
        oscillator.frequency.exponentialRampToValueAtTime(180, now + 0.16);

        gainNode.gain.setValueAtTime(0.0001, now);
        gainNode.gain.exponentialRampToValueAtTime(0.08, now + 0.015);
        gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.2);

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.start(now);
        oscillator.stop(now + 0.22);
        oscillator.addEventListener('ended', function () {
            if (typeof audioContext.close === 'function') {
                void audioContext.close();
            }
        });
    }

    function getCsrfToken() {
        const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (csrfInput instanceof HTMLInputElement && csrfInput.value) {
            return csrfInput.value;
        }

        const csrfCookie = document.cookie
            .split('; ')
            .find(function (cookie) {
                return cookie.startsWith('csrftoken=');
            });

        return csrfCookie ? decodeURIComponent(csrfCookie.split('=')[1]) : '';
    }

    async function ensureHandTracker() {
        if (handTrackerReady || typeof window.Hands !== 'function') {
            return;
        }

        handTracker = new window.Hands({
            locateFile: function (file) {
                return 'https://cdn.jsdelivr.net/npm/@mediapipe/hands/' + file;
            },
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
        currentHandLandmarks = landmarkSets.length ? landmarkSets[0] : [];

        landmarkSets.forEach(function (landmarks) {
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
        });

        overlayContext.restore();
    }

    function startHandTrackingLoop() {
        if (!cameraPreview || !handTrackerReady || handTrackingFrameId) {
            return;
        }

        const processFrame = async function () {
            if (!cameraPreview) {
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

    function startSignPredictionLoop() {
        if (signPredictionIntervalId || !predictUrl) {
            return;
        }

        signPredictionIntervalId = window.setInterval(function () {
            void runSignPrediction();
        }, 700);
    }

    function stopSignPredictionLoop() {
        if (signPredictionIntervalId) {
            window.clearInterval(signPredictionIntervalId);
            signPredictionIntervalId = 0;
        }

        signPredictionBusy = false;
    }

    async function runSignPrediction() {
        if (signPredictionBusy || !predictUrl || hasMatchedCorrectSign) {
            return;
        }

        const currentTerm = getCurrentTerm();

        if (!Array.isArray(currentHandLandmarks) || currentHandLandmarks.length < 21) {
            hideProceedButton();
            resetCorrectHold();
            renderDetectionMessage('Show your hand to start detection.', 'idle');
            return;
        }

        signPredictionBusy = true;

        try {
            const response = await fetch(predictUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify({
                    landmarks: currentHandLandmarks,
                }),
            });

            const payload = await response.json().catch(function () {
                return {};
            });

            if (!response.ok) {
                resetCorrectHold();
                renderDetectionMessage('Prediction unavailable for this lesson.', 'warning');
                return;
            }

            const predictedSign = String(payload.predicted_sign || '').replaceAll('_', ' ').trim();
            const confidence = Number(payload.confidence || 0);
            const confidencePercent = Math.round(confidence * 100);

            if (!predictedSign) {
                hideProceedButton();
                resetCorrectHold();
                lastAudibleOutcome = '';
                renderDetectionMessage('Sign not recognized yet.', 'warning');
                return;
            }

            if (confidence < 0.38) {
                hideProceedButton();
                resetCorrectHold();
                lastAudibleOutcome = '';
                renderDetectionMessage('Uncertain sign (' + confidencePercent + '%). Hold the sign steady.', 'warning');
                return;
            }

            if (predictedSign.toLowerCase() === currentTerm.toLowerCase()) {
                if (!correctHoldStartTime) {
                    correctHoldStartTime = Date.now();
                    lastHoldCountdownValue = 3;
                }

                const elapsedMs = Date.now() - correctHoldStartTime;
                const remainingMs = Math.max(0, correctHoldDurationMs - elapsedMs);
                const remainingSeconds = Math.max(1, Math.ceil(remainingMs / 1000));

                if (remainingMs > 0) {
                    if (lastHoldCountdownValue !== remainingSeconds) {
                        lastHoldCountdownValue = remainingSeconds;
                    }

                    renderDetectionMessage('Correct sign detected for ' + currentTerm + '. Hold for ' + remainingSeconds + ' more second' + (remainingSeconds === 1 ? '' : 's') + '.', 'success');
                    lastAudibleOutcome = '';
                    return;
                }

                hasMatchedCorrectSign = true;
                resetCorrectHold();
                playSuccessPing();
                revealProceedButton();
                stopCamera();
                if (cameraStatus) {
                    cameraStatus.textContent = 'Correct sign confirmed. Camera paused.';
                }
                lastAudibleOutcome = 'correct';
                renderDetectionMessage('Detected ' + predictedSign.toUpperCase() + ' (' + confidencePercent + '%). Good job.', 'success');
                return;
            }

            hideProceedButton();
            resetCorrectHold();
            if (lastAudibleOutcome !== 'incorrect') {
                playIncorrectBuzz();
                lastAudibleOutcome = 'incorrect';
            }
            renderDetectionMessage('Detected ' + predictedSign + ' (' + confidencePercent + '%). Try matching ' + currentTerm + '.', 'warning');
        } catch (error) {
            hideProceedButton();
            resetCorrectHold();
            lastAudibleOutcome = '';
            renderDetectionMessage('Prediction unavailable for this lesson.', 'warning');
        } finally {
            signPredictionBusy = false;
        }
    }

    async function startCamera() {
        if (!cameraPreview || !cameraStatus) {
            return;
        }

        const currentTerm = getCurrentTerm();

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            cameraStatus.textContent = 'Camera is not supported on this device.';
            return;
        }

        if (!window.isSecureContext) {
            cameraStatus.textContent = 'Camera requires HTTPS or localhost.';
            return;
        }

        cameraStatus.textContent = 'Opening camera...';

        try {
            stopCamera();
            cameraStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: 'user',
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
                audio: false,
            });

            cameraPreview.srcObject = cameraStream;
            await cameraPreview.play();
            cameraStatus.textContent = 'Mirror the hand shape for ' + currentTerm + '.';
            syncCameraOverlaySize();
            await ensureHandTracker();
            startHandTrackingLoop();
            startSignPredictionLoop();
        } catch (error) {
            cameraStatus.textContent = 'Unable to access your camera.';
        }
    }

    function stopCamera() {
        stopSignPredictionLoop();
        stopHandTrackingLoop();

        if (!cameraStream) {
            currentHandLandmarks = [];
            return;
        }

        cameraStream.getTracks().forEach(function (track) {
            track.stop();
        });
        if (cameraPreview) {
            cameraPreview.pause();
            cameraPreview.srcObject = null;
        }
        cameraStream = null;
        currentHandLandmarks = [];
    }

    if (restartCameraButton) {
        restartCameraButton.addEventListener('click', function () {
            hasMatchedCorrectSign = false;
            lastAudibleOutcome = '';
            resetCorrectHold();
            hideProceedButton();
            renderDetectionMessage('Show your hand to start detection.', 'idle');
            void startCamera();
        });
    }

    if (proceedButton) {
        proceedButton.addEventListener('click', function () {
            if (currentTermIndex >= syllabusTerms.length - 1) {
                hideProceedButton();
                renderDetectionMessage('All signs in this syllabus are completed.', 'success');
                if (cameraStatus) {
                    cameraStatus.textContent = 'Syllabus complete.';
                }
                return;
            }

            currentTermIndex += 1;
            hasMatchedCorrectSign = false;
            lastAudibleOutcome = '';
            resetCorrectHold();
            hideProceedButton();
            updateLessonLabels();
            renderDetectionMessage('Show your hand to start detection.', 'idle');
            void loadReferenceVideo();
            void startCamera();
        });
    }

    window.addEventListener('beforeunload', stopCamera);
    window.addEventListener('resize', syncCameraOverlaySize);

    updateLessonLabels();
    void loadReferenceVideo();
    hideProceedButton();
    renderDetectionMessage('Show your hand to start detection.', 'idle');
    void startCamera();
})();
