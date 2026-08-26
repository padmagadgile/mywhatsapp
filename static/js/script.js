document.addEventListener("DOMContentLoaded", () => {
    const currentUserId = document.body.getAttribute("data-current-user-id");
    const socket = io();

    const messageInput = document.getElementById("message-input");
    const sendButton = document.getElementById("send-button");
    const messagesContainer = document.getElementById("messages");
    const userElements = document.querySelectorAll(".user");
    const chatUserName = document.getElementById("chat-user-name");
    const chatAvatar = document.getElementById("chat-avatar");
    const chatStatus = document.getElementById("chat-status");
    const searchInput = document.getElementById("search-user-input");
const darkModeBtn = document.getElementById("dark-mode-btn");

// Check saved preference on load
if (localStorage.getItem("theme") === "dark") {
    document.body.classList.add("dark-theme");
    if (darkModeBtn) darkModeBtn.textContent = "☀️";
}

// Toggle on click
if (darkModeBtn) {
    darkModeBtn.addEventListener("click", () => {
        document.body.classList.toggle("dark-theme");
        const isDark = document.body.classList.contains("dark-theme");
        localStorage.setItem("theme", isDark ? "dark" : "light");
        darkModeBtn.textContent = isDark ? "☀️" : "🌙";
    });
}
    let selectedUserId = null;
    let typingTimeout = null;

    // --- SOCKET EVENTS ---
    socket.on("connect", () => {
        console.log("Connected to socket.");
    });





    

    // Live Online Status Updates
    socket.on("user_status", (data) => {
        const userEl = document.querySelector(`.user[data-id="${data.user_id}"]`);
        if (userEl) {
            const badge = userEl.querySelector(".status-dot");
            if (badge) {
                badge.className = `status-dot ${data.status}`;
            }
        }

        if (String(selectedUserId) === String(data.user_id)) {
            updateChatHeaderStatus(data.status === "online");
        }
    });

    // Live Typing Indicators
    socket.on("user_typing", (data) => {
        if (String(data.sender_id) === String(selectedUserId)) {
            if (data.is_typing) {
                chatStatus.textContent = "typing...";
                chatStatus.classList.add("typing-text");
            } else {
                const isOnline = document.querySelector(`.user[data-id="${selectedUserId}"] .status-dot`)?.classList.contains("online");
                updateChatHeaderStatus(isOnline);
            }
        }
    });

    // Receive Message & Update Unread Badges
    socket.on("receive_message", (data) => {
        const senderIdStr = String(data.sender_id);
        const receiverIdStr = String(data.receiver_id);
        const selectedIdStr = String(selectedUserId);
        const currentIdStr = String(currentUserId);

        if (
            (senderIdStr === selectedIdStr && receiverIdStr === currentIdStr) ||
            (senderIdStr === currentIdStr && receiverIdStr === selectedIdStr)
        ) {
            if (senderIdStr !== currentIdStr) {
                appendMessage(data.message, "received");
            }
        } else if (receiverIdStr === currentIdStr) {
            // Update unread badge for non-active conversation
            const senderUserEl = document.querySelector(`.user[data-id="${senderIdStr}"]`);
            if (senderUserEl) {
                let badge = senderUserEl.querySelector(".unread-badge");
                if (!badge) {
                    badge = document.createElement("span");
                    badge.className = "unread-badge";
                    badge.textContent = "0";
                    senderUserEl.querySelector(".user-info").appendChild(badge);
                }
                badge.textContent = parseInt(badge.textContent || "0") + 1;
                badge.style.display = "inline-block";
            }
        }
    });

    // --- USER SELECTION ---
    userElements.forEach((userEl) => {
        userEl.addEventListener("click", async () => {
            const userId = userEl.getAttribute("data-id");
            const userName = userEl.getAttribute("data-name");

            if (selectedUserId === userId) return;

            selectedUserId = userId;
            chatUserName.textContent = userName;
            if (chatAvatar) {
                chatAvatar.textContent = userName.charAt(0).toUpperCase();
            }

            // Update Header Online Status
            const isOnline = userEl.querySelector(".status-dot")?.classList.contains("online");
            updateChatHeaderStatus(isOnline);

            // Hide/Reset unread badge
            const badge = userEl.querySelector(".unread-badge");
            if (badge) {
                badge.textContent = "0";
                badge.style.display = "none";
            }

            userElements.forEach(el => el.classList.remove("active"));
            userEl.classList.add("active");

            await loadMessages(selectedUserId);
        });
    });

    function updateChatHeaderStatus(isOnline) {
        chatStatus.classList.remove("typing-text");
        chatStatus.textContent = isOnline ? "Online" : "Offline";
    }

    // --- SEARCH / FILTER USERS ---
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            const query = e.target.value.toLowerCase().trim();
            userElements.forEach((userEl) => {
                const name = userEl.getAttribute("data-name").toLowerCase();
                if (name.includes(query)) {
                    userEl.style.display = "flex";
                } else {
                    userEl.style.display = "none";
                }
            });
        });
    }

    // --- LOAD CHAT HISTORY ---
    async function loadMessages(userId) {
        try {
            const response = await fetch(`/messages/${userId}`);
            if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);

            const data = await response.json();
            if (!data.success) return;

            messagesContainer.innerHTML = "";

            if (data.messages.length === 0) {
                const emptyNotice = document.createElement("div");
                emptyNotice.className = "empty-notice";
                emptyNotice.textContent = "No previous messages. Say hi!";
                messagesContainer.appendChild(emptyNotice);
                return;
            }

            data.messages.forEach((msg) => {
                const type = String(msg.sender_id) === String(currentUserId) ? "sent" : "received";
                appendMessage(msg.message, type);
            });

            scrollToBottom();
        } catch (error) {
            console.error("Error fetching messages:", error);
        }
    }

    function appendMessage(text, type) {
        const emptyNotice = messagesContainer.querySelector(".empty-notice");
        if (emptyNotice) {
            emptyNotice.remove();
        }

        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", type);
        messageDiv.textContent = text;
        messagesContainer.appendChild(messageDiv);
        scrollToBottom();
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // --- SEND MESSAGE & TYPING EVENTS ---
    function sendMessage() {
        const text = messageInput.value.trim();

        if (!selectedUserId) {
            alert("Please select a user to chat with.");
            return;
        }

        if (!text) return;

        appendMessage(text, "sent");

        socket.emit("send_message", {
            receiver_id: selectedUserId,
            message: text
        });

        socket.emit("typing", { receiver_id: selectedUserId, is_typing: false });
        messageInput.value = "";
    }

    messageInput.addEventListener("input", () => {
        if (!selectedUserId) return;

        socket.emit("typing", { receiver_id: selectedUserId, is_typing: true });

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit("typing", { receiver_id: selectedUserId, is_typing: false });
        }, 1500);
    });

    sendButton.addEventListener("click", sendMessage);

    messageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            sendMessage();
        }
    });
});