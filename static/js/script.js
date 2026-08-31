document.addEventListener("DOMContentLoaded", () => {
    const currentUserId = document.body.getAttribute("data-current-user-id");
    const socket = io();

    // DOM Elements
    const messageInput = document.getElementById("message-input");
    const sendButton = document.getElementById("send-button");
    const messagesContainer = document.getElementById("messages");
    const userElements = document.querySelectorAll(".user");
    const chatUserName = document.getElementById("chat-user-name");
    const chatAvatar = document.getElementById("chat-avatar");
    const chatStatus = document.getElementById("chat-status");
    const searchInput = document.getElementById("search-user-input");
    const darkModeBtn = document.getElementById("dark-mode-btn");
    const attachBtn = document.getElementById("attach-btn");
    const fileInput = document.getElementById("file-input");
    const notificationSound = document.getElementById("notification-sound");

    // State Variables
    let selectedUserId = null;
    let typingTimeout = null;

    // --- 1. AUDIO UNLOCKER FOR BROWSER AUTOPLAY POLICY ---
    function enableAudioOnInteraction() {
        if (notificationSound) {
            notificationSound.play().then(() => {
                notificationSound.pause();
                notificationSound.currentTime = 0;
            }).catch(() => {});
        }
        document.removeEventListener('click', enableAudioOnInteraction);
        document.removeEventListener('keydown', enableAudioOnInteraction);
    }
    document.addEventListener('click', enableAudioOnInteraction);
    document.addEventListener('keydown', enableAudioOnInteraction);

    // --- 2. GLOBAL NOTIFICATION SETUP ---
    if ("Notification" in window && Notification.permission !== "granted") {
        Notification.requestPermission();
    }

    window.addEventListener("focus", () => {
        document.title = "Chat App";
    });

    // --- 3. DARK MODE LOGIC ---
    if (localStorage.getItem("theme") === "dark") {
        document.body.classList.add("dark-theme");
        if (darkModeBtn) darkModeBtn.textContent = "☀️";
    }

    if (darkModeBtn) {
        darkModeBtn.addEventListener("click", () => {
            document.body.classList.toggle("dark-theme");
            const isDark = document.body.classList.contains("dark-theme");
            localStorage.setItem("theme", isDark ? "dark" : "light");
            darkModeBtn.textContent = isDark ? "☀️" : "🌙";
        });
    }

    // --- 4. SOCKET EVENTS ---
    socket.on("connect", () => {
        console.log("Connected to socket server.");
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

    // Receive Real-time Message
    socket.on("receive_message", (data) => {
    const senderIdStr = String(data.sender_id);
    const receiverIdStr = String(data.receiver_id);
    const selectedIdStr = String(selectedUserId);
    const currentIdStr = String(currentUserId);

    // Only process if the current user is the recipient
    if (receiverIdStr === currentIdStr && senderIdStr !== currentIdStr) {
        
        const isTabHidden = document.hidden;
        const isDifferentChat = senderIdStr !== selectedIdStr;

        // Trigger Notification if user is away OR in a different chat tab
        if (isTabHidden || isDifferentChat) {
            
            // A. Play Audio Sound
            if (notificationSound) {
                notificationSound.play().catch(err => console.log("Audio playback blocked:", err));
            }

            // B. Flash Browser Tab Title
            document.title = "🔔 New message!";

            // C. Native Desktop/Mobile Push Notification
            if ("Notification" in window && Notification.permission === "granted") {
                
                // Get sender name from DOM
                const senderEl = document.querySelector(`.user[data-id="${senderIdStr}"]`);
                const senderName = senderEl ? senderEl.getAttribute("data-name") : "New Message";
                
                const notificationText = data.file_url 
                    ? "📷 Sent an attachment" 
                    : (data.message.length > 40 ? data.message.substring(0, 40) + "..." : data.message);

                const notification = new Notification(senderName, {
                    body: notificationText,
                    icon: "/static/icons/notification-icon.png", // Optional: Add custom icon path
                    tag: `chat-msg-${senderIdStr}` // Replaces old unread notifications from same user
                });

                // Auto open window and switch chat on click
                notification.onclick = function() {
                    window.focus();
                    if (senderEl) {
                        senderEl.click(); // Automatically opens the chat with sender
                    }
                    this.close();
                };
            }
        }
    }

    // --- UI UPDATING LOGIC ---
    if (
        (senderIdStr === selectedIdStr && receiverIdStr === currentIdStr) ||
        (senderIdStr === currentIdStr && receiverIdStr === selectedIdStr)
    ) {
        const messageType = senderIdStr === currentIdStr ? "sent" : "received";
        appendMessage(data.message, messageType, data.file_url, data.file_type, data.is_read || false);

        if (senderIdStr !== currentIdStr && !document.hidden) {
            socket.emit("mark_as_read", { sender_id: senderIdStr });
        }
    } else if (receiverIdStr === currentIdStr) {
        // Increment Unread Badge Counter in Sidebar
        const senderUserEl = document.querySelector(`.user[data-id="${senderIdStr}"]`);
        if (senderUserEl) {
            let badge = senderUserEl.querySelector(".unread-badge");
            if (!badge) {
                badge = document.createElement("span");
                badge.className = "unread-badge";
                badge.textContent = "0";
                const infoDiv = senderUserEl.querySelector(".user-info") || senderUserEl;
                infoDiv.appendChild(badge);
            }
            let count = parseInt(badge.textContent || "0") + 1;
            badge.textContent = count > 99 ? "99+" : count;
            badge.style.display = "inline-block";
        }
    }
});

    // Real-Time Blue Ticks Listener
    socket.on("messages_read", (data) => {
        if (String(selectedUserId) === String(data.read_by)) {
            document.querySelectorAll(".message.sent .tick").forEach(tick => {
                tick.textContent = "✓✓";
                tick.classList.add("blue-tick");
            });
        }
    });

    // --- 5. USER SELECTION ---
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

            // Reset unread badge
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

    // --- 6. SEARCH / FILTER USERS ---
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            const query = e.target.value.toLowerCase().trim();
            userElements.forEach((userEl) => {
                const name = userEl.getAttribute("data-name").toLowerCase();
                userEl.style.display = name.includes(query) ? "flex" : "none";
            });
        });
    }

    // --- 7. LOAD CHAT HISTORY ---
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
            } else {
                data.messages.forEach((msg) => {
                    const type = String(msg.sender_id) === String(currentUserId) ? "sent" : "received";
                    appendMessage(msg.message, type, msg.file_url, msg.file_type, msg.is_read || false);
                });
            }

            scrollToBottom();
        } catch (error) {
            console.error("Error fetching messages:", error);
        }
    }

    // --- 8. MESSAGE RENDERING (TEXT & FILES) ---
    function appendMessage(text, type, fileUrl = null, fileType = null, isRead = false) {
        const emptyNotice = messagesContainer.querySelector(".empty-notice");
        if (emptyNotice) {
            emptyNotice.remove();
        }

        const messageDiv = document.createElement("div");
        messageDiv.classList.add("message", type);

        let contentHtml = "";

        if (fileUrl) {
            if (fileType === "image") {
                contentHtml = `<img src="${fileUrl}" alt="Attachment" class="chat-image" style="max-width: 200px; border-radius: 8px; display: block; margin-bottom: 5px;">`;
            } else {
                contentHtml = `<a href="${fileUrl}" target="_blank" class="chat-file-link" style="color: inherit; text-decoration: underline;">📄 ${text || "Download File"}</a>`;
            }
        } else {
            contentHtml = `<span>${text}</span>`;
        }

        let ticksHtml = "";
        if (type === "sent") {
            const tickClass = isRead ? "tick blue-tick" : "tick";
            ticksHtml = `<span class="${tickClass}">${isRead ? "✓✓" : "✓"}</span>`;
        }

        messageDiv.innerHTML = `${contentHtml} ${ticksHtml}`;
        messagesContainer.appendChild(messageDiv);
        scrollToBottom();
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // --- 9. SEND MESSAGE & FILE ATTACHMENTS ---
    function sendMessage() {
        const text = messageInput.value.trim();

        if (!selectedUserId) {
            alert("Please select a user to chat with.");
            return;
        }

        if (!text) return;

        socket.emit("send_message", {
            receiver_id: selectedUserId,
            message: text
        });

        socket.emit("typing", { receiver_id: selectedUserId, is_typing: false });
        messageInput.value = "";
    }

    // File Upload Trigger
    if (attachBtn && fileInput) {
        attachBtn.addEventListener("click", () => fileInput.click());

        fileInput.addEventListener("change", async () => {
            if (!fileInput.files.length || !selectedUserId) return;

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("receiver_id", selectedUserId);

            try {
                const response = await fetch("/upload", {
                    method: "POST",
                    body: formData
                });
                const result = await response.json();
                if (!result.success) {
                    alert(result.error || "File upload failed.");
                }
            } catch (err) {
                console.error("Upload error:", err);
            } finally {
                fileInput.value = "";
            }
        });
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














userElements.forEach((userEl) => {
    userEl.addEventListener("click", async () => {
        const userId = userEl.getAttribute("data-id");
        
        // Hide/Clear Unread Badge Counter
        const badge = userEl.querySelector(".unread-badge");
        if (badge) {
            badge.textContent = "0";
            badge.style.display = "none";
        }

        // Reset Tab Title
        document.title = originalTitle;
    });
});