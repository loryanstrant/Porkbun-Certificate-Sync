// Dark mode, shared by index.html and the standalone auth pages.
//
// Kept separate from app.js because app.js registers listeners on index.html's
// DOM at load time and throws on any other page. Every element lookup here is
// null-safe for the same reason: the login and setup pages have no toggle button.

function toggleDarkMode() {
    const isDark = document.body.classList.toggle('dark-mode');
    document.documentElement.classList.toggle('dark-mode-preload', isDark);

    const icon = document.getElementById('dark-mode-icon');
    if (icon) {
        icon.textContent = isDark ? '☀️' : '🌙';
    }

    try {
        localStorage.setItem('darkMode', isDark ? 'enabled' : 'disabled');
    } catch (e) {
        // localStorage unavailable (private browsing); the toggle still works
        // for this page view.
    }
}

// Apply the stored preference on load.
(function () {
    let darkMode = null;
    try {
        darkMode = localStorage.getItem('darkMode');
    } catch (e) {
        return;
    }

    if (darkMode === 'enabled') {
        document.body.classList.add('dark-mode');
        const icon = document.getElementById('dark-mode-icon');
        if (icon) {
            icon.textContent = '☀️';
        }
    }
})();
