// Configuration
const BACKEND_URL = 'https://your-backend-url.onrender.com'; // TODO: Update this with your actual Render URL after deployment
let socket;
let currentUser = null;
let currentPrivateChat = null;

// DOM Elements
const authContainer = document.getElementById('auth-container');
const chatContainer = document.getElementById('chat-container');
const currentUserSpan = document.getElementById('current-user');
const messagesDiv = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const friendsList = document.getElementById('friends-list');
const privateMessagesDiv = document.getElementById('private-messages');
const privateMessageInput = document.getElementById('private-message-input');

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    checkAuthStatus();
});

function setupEventListeners() {
    // Auth forms
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    document.getElementById('register-form').addEventListener('submit', handleRegister);
    
    // Message input
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') sendMessage();
    });
    
    privateMessageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') sendPrivateMessage();
    });
}

// Authentication functions
async function handleLogin(e) {
    e.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentUser = username;
            showChat();
            initializeSocket();
            loadMessages();
            loadFriends();
            loadFriendRequests();
        } else {
            showAuthMessage(data.error, 'error');
        }
    } catch (error) {
        showAuthMessage('Login failed. Please try again.', 'error');
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = document.getElementById('register-username').value;
    const password = document.getElementById('register-password').value;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username, password }),
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showAuthMessage('Registration successful! Please log in.', 'success');
            showTab('login');
        } else {
            showAuthMessage(data.error, 'error');
        }
    } catch (error) {
        showAuthMessage('Registration failed. Please try again.', 'error');
    }
}

async function logout() {
    try {
        await fetch(`${BACKEND_URL}/api/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (error) {
        console.error('Logout error:', error);
    }
    
    currentUser = null;
    if (socket) {
        socket.disconnect();
    }
    showAuth();
}

function checkAuthStatus() {
    // For now, we'll just show the auth screen
    // In a real app, you'd check for existing session
    showAuth();
}

// UI Functions
function showAuth() {
    authContainer.style.display = 'flex';
    chatContainer.style.display = 'none';
}

function showChat() {
    authContainer.style.display = 'none';
    chatContainer.style.display = 'flex';
    currentUserSpan.textContent = currentUser;
}

function showTab(tab) {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const loginBtn = document.querySelector('.tab-btn:first-child');
    const registerBtn = document.querySelector('.tab-btn:last-child');
    
    if (tab === 'login') {
        loginForm.style.display = 'flex';
        registerForm.style.display = 'none';
        loginBtn.classList.add('active');
        registerBtn.classList.remove('active');
    } else {
        loginForm.style.display = 'none';
        registerForm.style.display = 'flex';
        loginBtn.classList.remove('active');
        registerBtn.classList.add('active');
    }
    
    showAuthMessage('', '');
}

function showSection(section) {
    const publicChat = document.getElementById('public-chat');
    const friendsSection = document.getElementById('friends-section');
    const privateChat = document.getElementById('private-chat');
    const navTabs = document.querySelectorAll('.nav-tab');
    
    navTabs.forEach(tab => tab.classList.remove('active'));
    event.target.classList.add('active');
    
    if (section === 'chat') {
        publicChat.style.display = 'flex';
        friendsSection.style.display = 'none';
        privateChat.style.display = 'none';
    } else if (section === 'friends') {
        publicChat.style.display = 'none';
        friendsSection.style.display = 'flex';
        privateChat.style.display = 'none';
        loadFriendRequests();
    }
}

function showAuthMessage(message, type) {
    const messageDiv = document.getElementById('auth-message');
    messageDiv.textContent = message;
    messageDiv.className = `message ${type}`;
}

// Socket.IO Functions
function initializeSocket() {
    socket = io(BACKEND_URL, {
        withCredentials: true
    });
    
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('message', (data) => {
        addMessage(data.user, data.msg, data.time);
    });
    
    socket.on('private_message', (data) => {
        if (currentPrivateChat) {
            addPrivateMessage(data.from, data.msg, data.time);
        }
    });
    
    socket.on('new_friend_request', (data) => {
        loadFriendRequests();
    });
    
    socket.on('friend_request_accepted', (data) => {
        loadFriends();
    });
}

// Message Functions
function sendMessage() {
    const message = messageInput.value.trim();
    if (message && socket) {
        socket.emit('message', { msg: message });
        messageInput.value = '';
    }
}

function sendPrivateMessage() {
    const message = privateMessageInput.value.trim();
    if (message && socket && currentPrivateChat) {
        socket.emit('private_message', { to: currentPrivateChat, msg: message });
        privateMessageInput.value = '';
    }
}

function addMessage(username, message, timestamp) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message-item ${username === currentUser ? 'own' : ''}`;
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <span>${username}</span>
            <span>${formatTime(timestamp)}</span>
        </div>
        <div class="message-text">${escapeHtml(message)}</div>
    `;
    
    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function addPrivateMessage(from, message, timestamp) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message-item ${from === 'You' ? 'own' : ''}`;
    
    messageDiv.innerHTML = `
        <div class="message-header">
            <span>${from}</span>
            <span>${formatTime(timestamp)}</span>
        </div>
        <div class="message-text">${escapeHtml(message)}</div>
    `;
    
    privateMessagesDiv.appendChild(messageDiv);
    privateMessagesDiv.scrollTop = privateMessagesDiv.scrollHeight;
}

// API Functions
async function loadMessages() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/messages`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            messagesDiv.innerHTML = '';
            data.messages.forEach(msg => {
                addMessage(msg.username, msg.message, msg.timestamp);
            });
        }
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

async function loadFriends() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/friends`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            displayFriends(data.friends);
        }
    } catch (error) {
        console.error('Error loading friends:', error);
    }
}

async function loadFriendRequests() {
    try {
        const response = await fetch(`${BACKEND_URL}/api/friend-requests`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            displayFriendRequests(data.pending_requests);
        }
    } catch (error) {
        console.error('Error loading friend requests:', error);
    }
}

async function searchUsers() {
    const query = document.getElementById('user-search').value.trim();
    if (query.length < 2) return;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/search-users?query=${encodeURIComponent(query)}`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            displaySearchResults(data.users);
        }
    } catch (error) {
        console.error('Error searching users:', error);
    }
}

async function sendFriendRequest(username) {
    try {
        const response = await fetch(`${BACKEND_URL}/api/send-friend-request/${username}`, {
            method: 'POST',
            credentials: 'include'
        });
        
        if (response.ok) {
            searchUsers(); // Refresh search results
        } else {
            const data = await response.json();
            alert(data.error);
        }
    } catch (error) {
        console.error('Error sending friend request:', error);
    }
}

async function respondToFriendRequest(reqId, action) {
    try {
        const response = await fetch(`${BACKEND_URL}/api/respond-friend-request/${reqId}/${action}`, {
            method: 'POST',
            credentials: 'include'
        });
        
        if (response.ok) {
            loadFriendRequests();
            loadFriends();
        }
    } catch (error) {
        console.error('Error responding to friend request:', error);
    }
}

async function openPrivateChat(friendUsername) {
    currentPrivateChat = friendUsername;
    document.getElementById('private-chat-friend').textContent = friendUsername;
    
    try {
        const response = await fetch(`${BACKEND_URL}/api/private-messages/${friendUsername}`, {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            privateMessagesDiv.innerHTML = '';
            data.messages.forEach(msg => {
                const from = msg.from_user === currentUser ? 'You' : msg.from_user;
                addPrivateMessage(from, msg.message, msg.timestamp);
            });
            
            // Show private chat
            document.getElementById('public-chat').style.display = 'none';
            document.getElementById('friends-section').style.display = 'none';
            document.getElementById('private-chat').style.display = 'flex';
        }
    } catch (error) {
        console.error('Error loading private messages:', error);
    }
}

function closePrivateChat() {
    currentPrivateChat = null;
    document.getElementById('public-chat').style.display = 'flex';
    document.getElementById('private-chat').style.display = 'none';
    showSection('chat');
}

// Display Functions
function displayFriends(friends) {
    friendsList.innerHTML = '';
    friends.forEach(friend => {
        const friendDiv = document.createElement('div');
        friendDiv.className = 'friend-item';
        friendDiv.textContent = friend;
        friendDiv.onclick = () => openPrivateChat(friend);
        friendsList.appendChild(friendDiv);
    });
}

function displaySearchResults(users) {
    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '';
    
    users.forEach(user => {
        const userDiv = document.createElement('div');
        userDiv.className = 'user-result';
        
        let buttonText = 'Add Friend';
        let buttonClass = 'add';
        let buttonDisabled = false;
        
        if (user.status === 'friend') {
            buttonText = 'Friends';
            buttonClass = 'friend';
            buttonDisabled = true;
        } else if (user.status === 'pending') {
            buttonText = 'Pending';
            buttonClass = 'pending';
            buttonDisabled = true;
        }
        
        userDiv.innerHTML = `
            <span>${escapeHtml(user.username)}</span>
            <button class="${buttonClass}" ${buttonDisabled ? 'disabled' : ''} 
                    onclick="sendFriendRequest('${escapeHtml(user.username)}')">
                ${buttonText}
            </button>
        `;
        
        resultsDiv.appendChild(userDiv);
    });
}

function displayFriendRequests(requests) {
    const requestsDiv = document.getElementById('friend-requests');
    requestsDiv.innerHTML = '';
    
    if (requests.length === 0) {
        requestsDiv.innerHTML = '<p>No pending friend requests</p>';
        return;
    }
    
    requests.forEach(request => {
        const requestDiv = document.createElement('div');
        requestDiv.className = 'request-item';
        requestDiv.innerHTML = `
            <span>${escapeHtml(request.from_user)}</span>
            <div>
                <button class="accept" onclick="respondToFriendRequest(${request.id}, 'accept')">
                    Accept
                </button>
                <button class="reject" onclick="respondToFriendRequest(${request.id}, 'reject')">
                    Reject
                </button>
            </div>
        `;
        requestsDiv.appendChild(requestDiv);
    });
}

// Utility Functions
function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
