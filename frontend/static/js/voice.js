function voiceRecorder() {
    let mediaRecorder = null;
    let chunks = [];

    return {
        recording: false,

        async toggleRecording() {
            if (this.recording) {
                this.stopRecording();
                return;
            }
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                chunks = [];

                mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
                mediaRecorder.onstop = () => {
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    this.transcribe(blob, 'recording.webm');
                    stream.getTracks().forEach((t) => t.stop());
                };

                mediaRecorder.start();
                this.recording = true;
            } catch (err) {
                this.$refs.fileInput.click();
            }
        },

        stopRecording() {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
            }
            this.recording = false;
        },

        uploadAudio(event) {
            const file = event.target.files[0];
            if (file) this.transcribe(file, file.name);
        },

        transcribe(blob, filename) {
            const formData = new FormData();
            formData.append('audio_file', blob, filename);
            formData.append('language', 'en');

            fetch('/api/voice/transcribe', {
                method: 'POST',
                body: formData,
            })
                .then((r) => r.text())
                .then((html) => {
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    const script = doc.querySelector('script');
                    if (script) eval(script.textContent);
                })
                .catch(() => {
                    if (typeof showNotification === 'function') {
                        showNotification('Voice transcription failed', 'error');
                    }
                });
        },
    };
}
