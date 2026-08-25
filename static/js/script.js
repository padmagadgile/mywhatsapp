const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const messages = document.getElementById("messages");

const users = document.querySelectorAll(".user");
const chatUserName = document.getElementById("chat-user-name");

let selectedUserId = null;


// ===============================
// SELECT CHAT USER
// ===============================

users.forEach(function(user) {

    user.addEventListener("click", async function() {

        const userId = user.getAttribute("data-id");
        const userName = user.getAttribute("data-name");

        selectedUserId = userId;

        chatUserName.textContent = userName;
        chatUserName.setAttribute("data-user-id", userId);

        console.log("Selected user:", userName);
        console.log("Receiver ID:", selectedUserId);

        await loadMessages(userId);

    });

});




async function loadMessages(userId) {

    try {

        const response = await fetch(`/messages/${userId}`);

        const data = await response.json();

        if (!data.success) {
            console.log("Error:", data.error);
            return;
        }

        // Clear current chat
        messages.innerHTML = "";

        data.messages.forEach(function(msg) {

            const message = document.createElement("div");

            if (msg.sender_id == userId) {
                message.classList.add("message", "received");
            } else {
                message.classList.add("message", "sent");
            }

            message.textContent = msg.message;

            messages.appendChild(message);

        });

        messages.scrollTop = messages.scrollHeight;

    } catch (error) {

        console.error("Error loading messages:", error);

    }

}








// ===============================
// SEND MESSAGE
// ===============================

async function sendMessage() {

    const messageText = messageInput.value.trim();

    if (!selectedUserId) {
        alert("Please select a user first.");
        return;
    }

    if (!messageText) {
        return;
    }


    try {

        const response = await fetch("/send_message", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                receiver_id: selectedUserId,
                message: messageText
            })

        });


        const data = await response.json();


        if (data.success) {

            console.log("Message saved:", data.message);

            // Show message on screen
            const message = document.createElement("div");

            message.classList.add("message", "sent");

            message.textContent = data.message;

            messages.appendChild(message);

            messageInput.value = "";

            messages.scrollTop = messages.scrollHeight;

        } else {

            console.log("Error:", data.error);

        }


    } catch (error) {

        console.error("Error sending message:", error);

    }

}


// ===============================
// SEND BUTTON
// ===============================

sendButton.addEventListener("click", sendMessage);


// ===============================
// PRESS ENTER TO SEND
// ===============================

messageInput.addEventListener("keydown", function(event) {

    if (event.key === "Enter") {

        event.preventDefault();

        sendMessage();

    }

});