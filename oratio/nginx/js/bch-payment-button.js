/* 
 * This script adds a Bitcoin Cash payment button to the Lemmy UI
 */
(function() {
    console.log("BCH Payment Button script loaded");
    
    // Wait for the navbar to be loaded
    function addPaymentButton() {
        // Try different navbar selectors
        const navbarSelectors = [
            '.nav-right',
            '.navbar-right',
            '.nav-bar-right',
            '.navbar .right',
            '.navbar-nav',
            'nav .right',
            'header nav',
            'header',
            'nav ul',
            '.nav-wrapper',
            '.header-right'
        ];
        
        let targetElement = null;
        
        // Try each selector to find a valid navbar element
        for (const selector of navbarSelectors) {
            const element = document.querySelector(selector);
            if (element) {
                console.log("Found navbar element with selector:", selector);
                targetElement = element;
                break;
            }
        }
        
        if (!targetElement) {
            console.log("Could not find any navbar element, will retry later");
            return false;
        }
        
        // Check if our button already exists
        if (!document.getElementById('bch-payment-button')) {
            console.log("Creating BCH payment button");
            
            // Create the button
            const paymentButton = document.createElement('a');
            paymentButton.id = 'bch-payment-button';
            paymentButton.href = 'https://payments.defadb.com/';
            paymentButton.className = 'btn btn-sm btn-success ml-2';
            paymentButton.target = '_blank';
            paymentButton.style.marginLeft = '10px';
            paymentButton.style.display = 'flex';
            paymentButton.style.alignItems = 'center';
            // Make it persist through DOM changes
            paymentButton.setAttribute('data-persist', 'true');
            
            // Add Bitcoin Cash icon and text
            paymentButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" style="margin-right: 5px;" viewBox="0 0 16 16">
                    <path d="M8 0C3.59 0 0 3.59 0 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8zm1.4 11.8c-.16.59-.82.85-1.39.58-.38-.18-.74-.58-.74-1.03 0-.19.05-.38.14-.55.09-.18.22-.33.38-.44.37-.27.88-.29 1.28-.07.4.22.64.65.63 1.09.01.15-.03.29-.09.42h.24zm-4.01-3.26c-.26-.13-.35-.5-.21-.76.14-.26.5-.37.76-.23.26.14.36.5.22.76-.14.26-.51.37-.77.23zm3.47-3.98c-.42-.15-.88-.08-1.26.14-.38.22-.66.6-.77 1.03l-.1.42h2.85l-.1-.42c-.11-.43-.4-.8-.78-1.03l.16-.14zm1.46 1.68h-4.55c-.25 0-.41.26-.32.49l.69 1.7c.14.33.41.66.77.89.43.27.94.37 1.43.27l.39-.08-1.11-2.54h2.28l-1.14 2.49.41.09c.5.1 1-.01 1.43-.28.35-.22.63-.55.76-.88l.69-1.7c.1-.23-.06-.46-.31-.46zm-4.4 4.58c.18-.11.39-.18.61-.19-.08-.21-.05-.45.07-.63.12-.18.32-.29.53-.29s.41.11.53.29c.12.18.16.42.07.63.22.01.43.08.61.19.18.11.33.27.41.47.08.2.09.41.03.61-.13.43-.58.72-1.05.67-.22-.02-.43-.11-.6-.26s-.28-.35-.3-.57c-.04-.47.27-.91.7-1.03.16-.05.33-.06.5-.02-.03-.1-.1-.17-.2-.21-.1-.04-.2-.04-.3 0-.1.04-.17.12-.2.21-.03.1-.03.2 0 .3.03.09.01.19-.06.25-.07.06-.17.08-.25.04s-.14-.12-.14-.21c0-.09.05-.17.13-.22z"/>
                </svg>
                Add BCH
            `;
            
            // Try to insert it at different positions
            try {
                // Insert before the last element (usually the settings/profile dropdown)
                if (targetElement.lastElementChild) {
                    targetElement.insertBefore(paymentButton, targetElement.lastElementChild);
                } else {
                    // Or just append it if there's no children
                    targetElement.appendChild(paymentButton);
                }
                console.log("BCH payment button added to navbar");
            } catch (e) {
                console.error("Error adding BCH button:", e);
                // As a fallback, try to add to the document body
                try {
                    // Create a floating button
                    paymentButton.style.position = 'fixed';
                    paymentButton.style.bottom = '20px';
                    paymentButton.style.right = '20px';
                    paymentButton.style.zIndex = '9999';
                    document.body.appendChild(paymentButton);
                    console.log("BCH payment button added as floating button");
                } catch (err) {
                    console.error("Final attempt failed:", err);
                }
            }
            return true;
        }
        return false;
    }
    
    // Add event listener to run our code after the DOM has loaded
    function init() {
        console.log("DOM content loaded, attempting to add button");
        
        // Try to add the button immediately
        if (!addPaymentButton()) {
            console.log("Button not added on first attempt, setting up retries");
            
            // Only create observer if document.body exists
            if (document.body) {
                console.log("Setting up mutation observer");
                const observer = new MutationObserver((mutations) => {
                    if (addPaymentButton()) {
                        console.log("Button added via observer, disconnecting");
                        observer.disconnect();
                    }
                });
                
                observer.observe(document.body, { 
                    childList: true, 
                    subtree: true 
                });
            } else {
                console.log("document.body not available yet, skipping observer");
            }
            
            // Also try again after delays as a fallback
            setTimeout(() => {
                if (addPaymentButton()) {
                    console.log("Button added via setTimeout (1.5s)");
                }
            }, 1500);
            
            setTimeout(() => {
                if (addPaymentButton()) {
                    console.log("Button added via setTimeout (3s)");
                }
            }, 3000);
            
            setTimeout(() => {
                if (addPaymentButton()) {
                    console.log("Button added via setTimeout (5s)");
                } else {
                    // Last resort: create a floating button if nothing else worked
                    try {
                        console.log("Creating floating button as last resort");
                        const floatingButton = document.createElement('a');
                        floatingButton.id = 'bch-payment-button';
                        floatingButton.href = 'http://localhost:8081/';
                        floatingButton.className = 'btn btn-success';
                        floatingButton.target = '_blank';
                        floatingButton.style.position = 'fixed';
                        floatingButton.style.bottom = '20px';
                        floatingButton.style.right = '20px';
                        floatingButton.style.zIndex = '9999';
                        floatingButton.style.padding = '8px 15px';
                        floatingButton.style.borderRadius = '4px';
                        floatingButton.style.textDecoration = 'none';
                        floatingButton.style.display = 'flex';
                        floatingButton.style.alignItems = 'center';
                        
                        floatingButton.innerHTML = `
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" style="margin-right: 5px;" viewBox="0 0 16 16">
                                <path d="M8 0C3.59 0 0 3.59 0 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8zm1.4 11.8c-.16.59-.82.85-1.39.58-.38-.18-.74-.58-.74-1.03 0-.19.05-.38.14-.55.09-.18.22-.33.38-.44.37-.27.88-.29 1.28-.07.4.22.64.65.63 1.09.01.15-.03.29-.09.42h.24zm-4.01-3.26c-.26-.13-.35-.5-.21-.76.14-.26.5-.37.76-.23.26.14.36.5.22.76-.14.26-.51.37-.77.23zm3.47-3.98c-.42-.15-.88-.08-1.26.14-.38.22-.66.6-.77 1.03l-.1.42h2.85l-.1-.42c-.11-.43-.4-.8-.78-1.03l.16-.14zm1.46 1.68h-4.55c-.25 0-.41.26-.32.49l.69 1.7c.14.33.41.66.77.89.43.27.94.37 1.43.27l.39-.08-1.11-2.54h2.28l-1.14 2.49.41.09c.5.1 1-.01 1.43-.28.35-.22.63-.55.76-.88l.69-1.7c.1-.23-.06-.46-.31-.46zm-4.4 4.58c.18-.11.39-.18.61-.19-.08-.21-.05-.45.07-.63.12-.18.32-.29.53-.29s.41.11.53.29c.12.18.16.42.07.63.22.01.43.08.61.19.18.11.33.27.41.47.08.2.09.41.03.61-.13.43-.58.72-1.05.67-.22-.02-.43-.11-.6-.26s-.28-.35-.3-.57c-.04-.47.27-.91.7-1.03.16-.05.33-.06.5-.02-.03-.1-.1-.17-.2-.21-.1-.04-.2-.04-.3 0-.1.04-.17.12-.2.21-.03.1-.03.2 0 .3.03.09.01.19-.06.25-.07.06-.17.08-.25.04s-.14-.12-.14-.21c0-.09.05-.17.13-.22z"/>
                            </svg>
                            Add BCH
                        `;
                        
                        document.body.appendChild(floatingButton);
                        console.log("Floating BCH button added as final fallback");
                    } catch (e) {
                        console.error("Failed to add floating button:", e);
                    }
                }
            }, 5000);
        }
        
        // Set up a periodic check to ensure the button remains
        // This is needed because Lemmy UI might remove our button during SPA navigation
        setInterval(() => {
            if (!document.getElementById('bch-payment-button')) {
                console.log("BCH payment button was removed, adding it again");
                addPaymentButton();
            }
        }, 2000); // Check every 2 seconds
    }

    // Wait for DOM to fully load before attaching our code
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
        console.log("Waiting for DOMContentLoaded event");
    } else {
        // DOM already loaded, run init directly
        console.log("DOM already loaded, running init now");
        init();
    }
    
    // Also set up a listener for SPA (Single Page Application) navigation
    // This helps with sites that use client-side routing
    window.addEventListener('popstate', () => {
        console.log("Navigation detected, checking if button exists");
        setTimeout(() => {
            if (!document.getElementById('bch-payment-button')) {
                console.log("Button missing after navigation, re-adding");
                addPaymentButton();
            }
        }, 500);
    });
    
    // Also try on various user interactions which might indicate page content changes
    document.addEventListener('click', () => {
        setTimeout(() => {
            if (!document.getElementById('bch-payment-button')) {
                console.log("Button missing after click, re-adding");
                addPaymentButton();
            }
        }, 500);
    });
    
    // Create a persistent floating button as a last resort
    // This button will stay fixed at bottom right corner
    function createPersistentButton() {
        // Only create if it doesn't exist already
        if (!document.getElementById('bch-payment-persistent')) {
            const floatingButton = document.createElement('a');
            floatingButton.id = 'bch-payment-persistent';
            floatingButton.href = 'http://localhost:8081/';
            floatingButton.className = 'btn btn-success';
            floatingButton.target = '_blank';
            floatingButton.style.position = 'fixed';
            floatingButton.style.bottom = '20px';
            floatingButton.style.right = '20px';
            floatingButton.style.zIndex = '9999';
            floatingButton.style.padding = '8px 15px';
            floatingButton.style.borderRadius = '4px';
            floatingButton.style.textDecoration = 'none';
            floatingButton.style.display = 'flex';
            floatingButton.style.alignItems = 'center';
            floatingButton.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';
            
            floatingButton.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" style="margin-right: 5px;" viewBox="0 0 16 16">
                    <path d="M8 0C3.59 0 0 3.59 0 8s3.59 8 8 8 8-3.59 8-8-3.59-8-8-8zm1.4 11.8c-.16.59-.82.85-1.39.58-.38-.18-.74-.58-.74-1.03 0-.19.05-.38.14-.55.09-.18.22-.33.38-.44.37-.27.88-.29 1.28-.07.4.22.64.65.63 1.09.01.15-.03.29-.09.42h.24zm-4.01-3.26c-.26-.13-.35-.5-.21-.76.14-.26.5-.37.76-.23.26.14.36.5.22.76-.14.26-.51.37-.77.23zm3.47-3.98c-.42-.15-.88-.08-1.26.14-.38.22-.66.6-.77 1.03l-.1.42h2.85l-.1-.42c-.11-.43-.4-.8-.78-1.03l.16-.14zm1.46 1.68h-4.55c-.25 0-.41.26-.32.49l.69 1.7c.14.33.41.66.77.89.43.27.94.37 1.43.27l.39-.08-1.11-2.54h2.28l-1.14 2.49.41.09c.5.1 1-.01 1.43-.28.35-.22.63-.55.76-.88l.69-1.7c.1-.23-.06-.46-.31-.46zm-4.4 4.58c.18-.11.39-.18.61-.19-.08-.21-.05-.45.07-.63.12-.18.32-.29.53-.29s.41.11.53.29c.12.18.16.42.07.63.22.01.43.08.61.19.18.11.33.27.41.47.08.2.09.41.03.61-.13.43-.58.72-1.05.67-.22-.02-.43-.11-.6-.26s-.28-.35-.3-.57c-.04-.47.27-.91.7-1.03.16-.05.33-.06.5-.02-.03-.1-.1-.17-.2-.21-.1-.04-.2-.04-.3 0-.1.04-.17.12-.2.21-.03.1-.03.2 0 .3.03.09.01.19-.06.25-.07.06-.17.08-.25.04s-.14-.12-.14-.21c0-.09.05-.17.13-.22z"/>
                </svg>
                Add BCH
            `;
            
            document.body.appendChild(floatingButton);
            console.log("Persistent floating BCH button added");
        }
    }
    
    // Add the persistent button after a delay
    setTimeout(createPersistentButton, 8000);
})();