const chatArea = document.getElementById('chat-area');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const attachBtn = document.getElementById('attach-btn');
const fileInput = document.getElementById('file-input');
const imageModeBtn = document.getElementById('image-mode-btn');
const voiceAgentBtn = document.getElementById('voice-agent-btn');
const toast = document.getElementById('toast');

let imageMode = false;
let voiceAgentActive = false;
let speechRecognition = null;
let synth = window.speechSynthesis;

// Initialize Speech Recognition if supported
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.lang = 'en-US';

    speechRecognition.onresult = function (event) {
        const text = event.results[0][0].transcript;
        messageInput.value = text;
        addMessage(text, 'user');
        sendMessageToBackend(text);
    };

    speechRecognition.onend = function () {
        if (voiceAgentActive) {
            voiceAgentBtn.classList.remove('active');
            voiceAgentActive = false;
        }
    };

    speechRecognition.onerror = function (event) {
        console.error("Speech recognition error", event.error);
        showToast("Speech Recognition Error: " + event.error);
        voiceAgentBtn.classList.remove('active');
        voiceAgentActive = false;
    };
} else {
    console.warn("Speech recognition not supported in this browser.");
}

// Toggles
imageModeBtn.addEventListener('click', () => {
    imageMode = !imageMode;
    imageModeBtn.classList.toggle('active', imageMode);
    if (imageMode) {
        messageInput.placeholder = "Generate image: Describe what you want...";
    } else {
        messageInput.placeholder = "Ask me anything...";
    }
});

voiceAgentBtn.addEventListener('click', () => {
    if (!speechRecognition) {
        alert("Speech recognition is not supported in your browser. Please try Chrome or Edge.");
        return;
    }
    if (voiceAgentActive) {
        speechRecognition.stop();
        voiceAgentBtn.classList.remove('active');
        voiceAgentActive = false;
    } else {
        synth.cancel(); // Stop any currently speaking voice
        speechRecognition.start();
        voiceAgentBtn.classList.add('active');
        voiceAgentActive = true;
        showToast("Listening... Speak now!");
    }
});

// Trigger file input click
attachBtn.addEventListener('click', () => {
    fileInput.click();
});

// Upload file
fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    // Add loading / info bubble
    addMessage(`Uploading and indexing: ${file.name}...`, 'user');
    const typingId = showTypingIndicator();

    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        removeTypingIndicator(typingId);

        if (res.ok) {
            addMessage(`File '${file.name}' processed successfully.`, 'bot');
            showToast(`File processed successfully.`);
        } else {
            addMessage(`Error processing file: ${data.error}`, 'bot');
        }
    } catch (err) {
        removeTypingIndicator(typingId);
        console.error(err);
        addMessage("Failed to connect to backend server.", 'bot');
    }
    fileInput.value = ''; // clear input
});

// Handle text message submission
sendBtn.addEventListener('click', handleSend);
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        handleSend();
    }
});

function handleSend() {
    const text = messageInput.value.trim();
    if (!text) return;

    addMessage(text, 'user');
    messageInput.value = '';
    sendMessageToBackend(text);
}

async function sendMessageToBackend(text) {
    const typingId = showTypingIndicator();
    const endpoint = imageMode ? '/generate_image' : '/query';
    const body = imageMode ? { prompt: text } : { query: text };

    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await res.json();
        removeTypingIndicator(typingId);

        if (res.ok) {
            if (imageMode) {
                // Display image response
                const caption = `Here is your generated image: "${text}"`;
                addMessage(caption, 'bot', data.image_url);
                // Reset image mode after generating to match standard behavior
                imageMode = false;
                imageModeBtn.classList.remove('active');
                messageInput.placeholder = "Ask me anything...";
            } else {
                // Display RAG or general answer
                addMessage(data.answer, 'bot');
                // Speak back the response if voice agent was used/is active
                if (voiceAgentActive || voiceAgentBtn.classList.contains('active')) {
                    speakText(data.answer);
                }
            }
        } else {
            addMessage(`Error: ${data.error}`, 'bot');
        }
    } catch (err) {
        removeTypingIndicator(typingId);
        console.error(err);
        addMessage("Error connecting to the backend server.", 'bot');
    }
}

function addMessage(text, sender, imageUrl = null) {
    const row = document.createElement('div');
    row.classList.add('message-row', sender);

    const avatar = document.createElement('div');
    avatar.classList.add('msg-avatar');
    avatar.innerHTML = sender === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';

    const container = document.createElement('div');
    container.classList.add('msg-bubble-container');

    const bubble = document.createElement('div');
    bubble.classList.add('msg-bubble');
    bubble.textContent = text;

    if (imageUrl) {
        const img = document.createElement('img');
        img.classList.add('msg-image');
        img.src = imageUrl;
        img.alt = "Generated Image";
        bubble.appendChild(img);
    }

    const time = document.createElement('div');
    time.classList.add('msg-time');
    const now = new Date();
    let hours = now.getHours();
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'pm' : 'am';
    hours = hours % 12;
    hours = hours ? hours : 12; // the hour '0' should be '12'
    time.textContent = `${hours}:${minutes} ${ampm}`;

    container.appendChild(bubble);
    container.appendChild(time);
    row.appendChild(avatar);
    row.appendChild(container);

    chatArea.appendChild(row);
    chatArea.scrollTop = chatArea.scrollHeight;
}

function showTypingIndicator() {
    const id = 'typing-' + Date.now();
    const row = document.createElement('div');
    row.classList.add('message-row', 'bot');
    row.id = id;

    const avatar = document.createElement('div');
    avatar.classList.add('msg-avatar');
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';

    const container = document.createElement('div');
    container.classList.add('msg-bubble-container');

    const bubble = document.createElement('div');
    bubble.classList.add('msg-bubble');

    const indicator = document.createElement('div');
    indicator.classList.add('typing-indicator');
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.classList.add('typing-dot');
        indicator.appendChild(dot);
    }

    bubble.appendChild(indicator);
    container.appendChild(bubble);
    row.appendChild(avatar);
    row.appendChild(container);

    chatArea.appendChild(row);
    chatArea.scrollTop = chatArea.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const indicator = document.getElementById(id);
    if (indicator) {
        indicator.remove();
    }
}

function showToast(message) {
    toast.textContent = message;
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

function speakText(text) {
    if (!synth) return;
    // Clean markdown syntax or bold tags before speaking
    const cleanText = text.replace(/[*#`_\-]/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = 'en-US';
    synth.speak(utterance);
}