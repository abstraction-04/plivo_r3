// InspireWorks Frontend Logic

document.addEventListener('DOMContentLoaded', () => {
  const callForm = document.getElementById('call-form');
  const phoneNumberInput = document.getElementById('phoneNumber');
  const submitBtn = document.getElementById('submit-btn');
  const btnText = submitBtn.querySelector('.btn-text');
  const btnLoader = submitBtn.querySelector('.btn-loader');
  const callStatusBox = document.getElementById('call-status-box');
  const callStatusLabel = document.getElementById('call-status-label');
  const resetCallBtn = document.getElementById('reset-call-btn');
  const clearLogsBtn = document.getElementById('clear-logs-btn');
  const terminalContent = document.getElementById('terminal-content');
  const tunnelBadge = document.getElementById('tunnel-badge');
  const tunnelStatusText = document.getElementById('tunnel-status-text');

  let eventSource = null;

  // 1. Establish SSE Event Stream Connection
  function connectEventStream() {
    if (eventSource) {
      eventSource.close();
    }

    eventSource = new EventSource('/api/events');

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleLogEvent(payload);
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('SSE Connection failed. Reconnecting in 3s...', err);
      eventSource.close();
      setTimeout(connectEventStream, 3000);
    };
  }

  // 2. Poll Ngrok Status
  async function checkTunnelStatus() {
    try {
      const res = await fetch('/api/tunnel-status');
      if (res.ok) {
        const data = await res.json();
        if (data.publicUrl) {
          tunnelBadge.className = 'tunnel-badge status-connected';
          tunnelStatusText.textContent = `Ngrok Online: ${data.publicUrl.replace('https://', '')}`;
        } else {
          tunnelBadge.className = 'tunnel-badge status-disconnected';
          tunnelStatusText.textContent = 'Ngrok Offline (Check Port 5000)';
        }
      }
    } catch (err) {
      tunnelBadge.className = 'tunnel-badge status-disconnected';
      tunnelStatusText.textContent = 'Server Offline';
    }
  }

  // Poll tunnel status every 5 seconds
  checkTunnelStatus();
  setInterval(checkTunnelStatus, 5000);

  // Connect SSE on load
  connectEventStream();

  // 3. Initiate Call Form Submission
  callForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const phoneNumber = phoneNumberInput.value.trim();

    // Reset UI states
    submitBtn.disabled = true;
    btnLoader.classList.remove('hidden');
    btnText.textContent = 'Initiating...';
    callStatusBox.classList.remove('hidden');
    callStatusLabel.textContent = 'Routing call via Plivo...';

    try {
      const response = await fetch('/api/make-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phoneNumber })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to trigger outbound call');
      }

      callStatusLabel.textContent = 'Calling your phone...';
    } catch (error) {
      addLogLine('event-error', `System Error: ${error.message}`);
      callStatusLabel.textContent = 'Call failed to start.';
      submitBtn.disabled = false;
      btnLoader.classList.add('hidden');
      btnText.textContent = 'Initiate IVR Call';
    }
  });

  // Reset call button
  resetCallBtn.addEventListener('click', () => {
    submitBtn.disabled = false;
    btnLoader.classList.add('hidden');
    btnText.textContent = 'Initiate IVR Call';
    callStatusBox.classList.add('hidden');
  });

  // Clear logs button
  clearLogsBtn.addEventListener('click', () => {
    terminalContent.innerHTML = '<div class="log-line system-msg">[System] Console cleared. Ready.</div>';
  });

  // 4. Log Event Handler
  function handleLogEvent(payload) {
    const { type, data, timestamp } = payload;
    const timeStr = new Date(timestamp).toLocaleTimeString();
    
    let cssClass = 'system-msg';
    let text = '';

    switch (type) {
      case 'call_initiating':
        cssClass = 'event-initiating';
        text = `Initiating outbound call to ${data.to} from Plivo verified caller ID ${data.from}...`;
        break;
      case 'call_initiated':
        cssClass = 'event-initiated';
        text = `Call placed successfully. CallUUID: ${data.callUuid}. Awaiting response from target ${data.to}...`;
        callStatusLabel.textContent = 'Call ringing...';
        break;
      case 'call_answered':
        cssClass = 'event-answered';
        text = `Recipient answered! CallUUID: ${data.callUuid}. Greeting caller and requesting 4-digit security PIN...`;
        callStatusLabel.textContent = 'In Call: Authentication';
        break;
      case 'otp_received':
        cssClass = 'event-otp-received';
        text = `User entered DTMF PIN digits: [${data.digits}]. Verifying correctness...`;
        break;
      case 'otp_success':
        cssClass = 'event-otp-success';
        text = `Verification successful! PIN matches hardcoded birthdate. Forwarding to Level 1 Menu (Language Selection)...`;
        callStatusLabel.textContent = 'In Call: Language Selection';
        break;
      case 'otp_failed':
        cssClass = 'event-otp-failed';
        text = `Verification failed! Entered PIN [${data.digits}] is incorrect. Re-prompting security code...`;
        break;
      case 'language_selected':
        cssClass = 'event-otp-received';
        text = `User entered DTMF digit: [${data.digits}] for language selection.`;
        break;
      case 'language_confirmed':
        cssClass = 'event-lang-confirmed';
        text = `Language selection confirmed: [${data.lang.toUpperCase()}]. Presenting Level 2 options (1: Play Audio, 2: Dial Associate)...`;
        callStatusLabel.textContent = `In Call: Level 2 (${data.lang.toUpperCase()})`;
        break;
      case 'language_invalid':
        cssClass = 'event-otp-failed';
        text = `Invalid language input [${data.digits}] received. Re-prompting English (1) or Spanish (2)...`;
        break;
      case 'level2_selected':
        cssClass = 'event-otp-received';
        text = `User entered DTMF digit: [${data.digits}] for Level 2 action branching.`;
        break;
      case 'playing_audio':
        cssClass = 'event-playing-audio';
        text = `Action 1: Playing audio file (https://s3.amazonaws.com/static.plivo.com/music.mp3). Call will terminate on completion.`;
        callStatusLabel.textContent = 'In Call: Playing Audio';
        break;
      case 'connecting_associate':
        cssClass = 'event-connecting-associate';
        text = `Action 2: Forwarding call to Live Associate at ${data.associate}...`;
        callStatusLabel.textContent = 'In Call: Forwarding Call';
        break;
      case 'level2_invalid':
        cssClass = 'event-otp-failed';
        text = `Invalid menu input [${data.digits}] received in Level 2. Re-prompting options...`;
        break;
      case 'call_error':
        cssClass = 'event-error';
        text = `Error: ${data.error}`;
        callStatusLabel.textContent = 'Call error occurred.';
        resetUi();
        break;
      case 'call_status':
        cssClass = 'system-msg';
        text = `Plivo Call Status Update: ${data.status}`;
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'no-answer') {
          callStatusLabel.textContent = `Call ended (${data.status}).`;
          resetUi();
        }
        break;
      default:
        text = `${type}: ${JSON.stringify(data)}`;
    }

    addLogLine(cssClass, text, timeStr);
  }

  function addLogLine(cssClass, text, timeStr = null) {
    if (!timeStr) {
      timeStr = new Date().toLocaleTimeString();
    }
    const logDiv = document.createElement('div');
    logDiv.className = `log-line ${cssClass}`;
    logDiv.innerHTML = `<span class="log-time">[${timeStr}]</span> ${text}`;
    terminalContent.appendChild(logDiv);
    
    // Auto scroll to bottom
    terminalContent.scrollTop = terminalContent.scrollHeight;
  }

  function resetUi() {
    submitBtn.disabled = false;
    btnLoader.classList.add('hidden');
    btnText.textContent = 'Initiate IVR Call';
  }
});
