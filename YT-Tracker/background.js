chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Standardize on 127.0.0.1 to match manifest permissions
    fetch('http://127.0.0.1:5000/youtube/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(message)
    })
    .then(response => {
        if (!response.ok) throw new Error("Flask rejected data");
        console.log("Sent to Python:", message.title);
    })
    .catch(err => console.log("Server not reached. Is App.py running?"));
    
    return true; 
});