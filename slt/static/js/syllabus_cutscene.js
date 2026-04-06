(function () {
    const cutscene = document.getElementById('site-cutscene');
    if (!cutscene) {
        return;
    }

    const titleNode = cutscene.querySelector('.site-cutscene__title');
    const captionNode = cutscene.querySelector('.site-cutscene__caption');
    const skipButton = document.getElementById('site-cutscene-skip');

    const titleText = cutscene.dataset.cutsceneTitle || 'Syllabus';
    const captionText = cutscene.dataset.cutsceneCaption || 'Your Contribution To Society Is Filled With Determination';

    if (titleNode) {
        titleNode.textContent = titleText;
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const avatarDelay = prefersReducedMotion ? 80 : 420;
    const startTypingDelay = prefersReducedMotion ? 120 : 950;
    const charInterval = prefersReducedMotion ? 6 : 45;
    const holdAfterTyping = prefersReducedMotion ? 260 : 1100;

    document.body.classList.add('cutscene-lock');

    let hidden = false;
    let finishTimerId = null;
    let typeIntervalId = null;
    let startedHiding = false;

    function renderTypewriter(text) {
        if (!captionNode) {
            return Promise.resolve();
        }

        captionNode.textContent = '';
        let index = 0;

        return new Promise(function (resolve) {
            typeIntervalId = window.setInterval(function () {
                if (hidden) {
                    window.clearInterval(typeIntervalId);
                    typeIntervalId = null;
                    resolve();
                    return;
                }

                index += 1;
                const done = index >= text.length;
                const visibleText = text.slice(0, Math.min(index, text.length));

                if (done) {
                    captionNode.textContent = visibleText;
                    window.clearInterval(typeIntervalId);
                    typeIntervalId = null;
                    resolve();
                    return;
                }

                captionNode.innerHTML = visibleText + '<span class="site-cutscene__cursor">|</span>';
            }, charInterval);
        });
    }

    function hideCutscene() {
        if (hidden) {
            return;
        }

        startedHiding = true;
        hidden = true;
        cutscene.classList.add('site-cutscene--hidden');
        document.body.classList.remove('cutscene-lock');

        window.setTimeout(function () {
            if (cutscene.parentNode) {
                cutscene.parentNode.removeChild(cutscene);
            }
        }, 460);

        if (finishTimerId) {
            window.clearTimeout(finishTimerId);
        }

        if (typeIntervalId) {
            window.clearInterval(typeIntervalId);
        }

        document.removeEventListener('keydown', onKeyDown);
    }

    function onKeyDown(event) {
        if (event.key === 'Escape') {
            hideCutscene();
        }
    }

    if (skipButton) {
        skipButton.addEventListener('click', hideCutscene);
    }

    document.addEventListener('keydown', onKeyDown);

    window.setTimeout(function () {
        if (!hidden) {
            cutscene.classList.add('site-cutscene--avatar');
        }
    }, avatarDelay);

    window.setTimeout(function () {
        if (hidden) {
            return;
        }

        cutscene.classList.add('site-cutscene--typing');

        renderTypewriter(captionText).then(function () {
            if (hidden || startedHiding) {
                return;
            }

            finishTimerId = window.setTimeout(hideCutscene, holdAfterTyping);
        });
    }, startTypingDelay);
})();
