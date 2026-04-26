setInterval(() => {
    // Finds the video player on the page
    const video = document.querySelector('video');
    
    // Only runs if the video exists and is currently playing
    if (video && !video.paused) { 
        const time = Math.floor(video.currentTime); // Gets current second
        const urlParams = new URLSearchParams(window.location.search);
        const videoId = urlParams.get('v'); // Gets the 11-character video ID

        if (videoId) {
            // Cleans the tab title
            const cleanTitle = document.title.replace(" - YouTube", ""); 
            
            // Finds the channel name in the YouTube UI
            const channelName = document.querySelector('#owner #channel-name a')?.innerText || "";

            // CRITICAL: These must be BACKTICKS ` ` (not single quotes) for the ${} to work
            const fullUrl = `https://www.youtube.com/watch?v=${videoId}&t=${time}s`; 

            // Sends the data packet to background.js
            chrome.runtime.sendMessage({
                title: cleanTitle,
                channel: channelName,
                url: fullUrl
            });
        }
    }
}, 3000); // Sends an update every 3 seconds