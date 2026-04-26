setInterval(() => {
    const video = document.querySelector('video');
    const urlParams = new URLSearchParams(window.location.search);
    const currentId = urlParams.get('v');

    // 1. Send PC state to Phone
    if (video && !video.paused && currentId) {
        try {
            chrome.runtime.sendMessage({
                title: document.title.replace(" - YouTube", ""),
                channel: document.querySelector('#owner #channel-name a')?.innerText || "",
                url: `https://www.youtube.com/watch?v=${currentId}&t=${Math.floor(video.currentTime)}s`
            });
        } catch (e) { }
    }

    // 2. Probing for Sync Commands
    fetch('http://127.0.0.1:5000/youtube/check_sync')
    .then(res => res.json())
    .then(data => {
        if (data.sync === true && currentId) {
            console.log("--- SYNC START ---");
            
            fetch('https://www.youtube.com/feed/history')
            .then(res => res.text())
            .then(html => {
                // DEBUG: Let's see if the Video ID even exists in the history HTML
                console.log("Is current Video ID in history HTML?:", html.includes(currentId));

                const sections = html.split('videoRenderer');
                let foundTime = null;

                for (let section of sections) {
                    if (section.includes(currentId)) {
                        // NEW REGEX: Handles "at 10:05", "10:05", and "Resume at 10:05"
                        const match = section.match(/(\d+):(\d+)(?::(\d+))?"\}\},"accessibleContext"/);
                        
                        if (match) {
                            console.log("Raw match found:", match[0]);
                            if (match[3]) { // H:MM:SS
                                foundTime = (parseInt(match[1]) * 3600) + (parseInt(match[2]) * 60) + parseInt(match[3]);
                            } else { // MM:SS
                                foundTime = (parseInt(match[1]) * 60) + parseInt(match[2]);
                            }
                            break; 
                        }
                    }
                }

                if (foundTime && video) {
                    console.log("SUCCESS: Calculated seconds:", foundTime);
                    video.currentTime = foundTime;
                } else {
                    console.warn("FAILED: No timestamp found in history block. Defaulting to reload.");
                    location.reload(); 
                }
            });
        }
    });
}, 3000);