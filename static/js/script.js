const messageInput = document.getElementById("message-input");
const sendButton = document.getElementById("send-button");
const messages = document.getElementById("messages");


// SEND MESSAGE
function sendMessage() {

    const messageText = messageInput.value.trim();

    if (messageText === "") {
        return;
    }

    const message = document.createElement("div");

    message.classList.add("message", "sent");

    message.textContent = messageText;

    messages.appendChild(message);

    messageInput.value = "";

    messages.scrollTop = messages.scrollHeight;
}


// Send button click
sendButton.addEventListener("click", sendMessage);


// Press Enter to send
messageInput.addEventListener("keydown", function(event) {

    if (event.key === "Enter") {
        sendMessage();
    }

});


// CHANGE CHAT USER
const users = document.querySelectorAll(".user");

const chatUserName = document.getElementById("chat-user-name");

users.forEach(function(user) {

    user.addEventListener("click", function() {

        const name = user.getAttribute("data-name");

        chatUserName.textContent = name;

    });

});