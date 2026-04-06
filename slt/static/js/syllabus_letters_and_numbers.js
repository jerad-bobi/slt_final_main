(function () {
    const lesson = document.querySelector('.syllabus-lesson');
    if (!lesson) {
        return;
    }

    const lookupUrl = lesson.dataset.lookupUrl || '';
    const predictUrl = lesson.dataset.predictUrl || '';
    const term = lesson.dataset.term || 'A';
    const videoShell = document.getElementById('syllabus-video-shell');
    const cameraPreview = document.getElementById('syllabus-camera-preview');
    const cameraOverlay = document.getElementById('syllabus-camera-overlay');
    const cameraStatus = document.getElementById('syllabus-camera-status');
    const detectionOutput = document.getElementById('syllabus-detection-output');
    const restartCameraButton = document.getElementById('syllabus-restart-camera');
    const overlayContext = cameraOverlay ? cameraOverlay.getContext('2d') : null;

    let cameraStream = null;
    let handTracker = null;
    let handTrackerReady = false;
    let handTrackingFrameId = 0;
    let handTrackingBusy = false;
    let signPredictionIntervalId = 0;
    let signPredictionBusy = false;
    let currentHandLandmarks = [];

    async function loadReferenceVideo() {
        if (!lookupUrl || !videoShell) {
            return;
        }

        try {
            const response = await fetch(lookupUrl + '?text=' + encodeURIComponent(term), {
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
        if (signPredictionBusy || !predictUrl) {
            return;
        }

        if (!Array.isArray(currentHandLandmarks) || currentHandLandmarks.length < 21) {
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
                renderDetectionMessage('Prediction unavailable for this lesson.', 'warning');
                return;
            }

            const predictedSign = String(payload.predicted_sign || '').replaceAll('_', ' ').trim();
            const confidence = Number(payload.confidence || 0);
            const confidencePercent = Math.round(confidence * 100);

            if (!predictedSign) {
                renderDetectionMessage('Sign not recognized yet.', 'warning');
                return;
            }

            if (confidence < 0.38) {
                renderDetectionMessage('Uncertain sign (' + confidencePercent + '%). Hold the sign steady.', 'warning');
                return;
            }

            if (predictedSign.toLowerCase() === term.toLowerCase()) {
                renderDetectionMessage('Detected ' + predictedSign.toUpperCase() + ' (' + confidencePercent + '%). Good job.', 'success');
                return;
            }

            renderDetectionMessage('Detected ' + predictedSign + ' (' + confidencePercent + '%). Try matching ' + term + '.', 'warning');
        } catch (error) {
            renderDetectionMessage('Prediction unavailable for this lesson.', 'warning');
        } finally {
            signPredictionBusy = false;
        }
    }

    async function startCamera() {
        if (!cameraPreview || !cameraStatus) {
            return;
        }

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
            cameraStatus.textContent = 'Mirror the hand shape for letter ' + term + '.';
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
        cameraStream = null;
        currentHandLandmarks = [];
    }

    if (restartCameraButton) {
        restartCameraButton.addEventListener('click', function () {
            void startCamera();
        });
    }

    window.addEventListener('beforeunload', stopCamera);
    window.addEventListener('resize', syncCameraOverlaySize);

    void loadReferenceVideo();
    renderDetectionMessage('Show your hand to start detection.', 'idle');
    void startCamera();
})();
