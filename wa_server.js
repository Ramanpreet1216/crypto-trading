const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers } = require('@whiskeysockets/baileys');
const express = require('express');
const QRCode = require('qrcode');
const pino = require('pino');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(express.json());

let sock = null;
let currentQR = null;
let pairingCode = null;
let isConnected = false;
const authFolder = path.join(__dirname, 'auth_info');
const TARGET_PHONE = '919478551925';

async function connectToWhatsApp() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState(authFolder);
        sock = makeWASocket({
            auth: state,
            logger: pino({ level: 'silent' }),
            printQRInTerminal: false,
            browser: Browsers ? Browsers.ubuntu('Chrome') : ['Ubuntu', 'Chrome', '20.0.04']
        });

        // If not registered, request pairing code for phone number
        if (!sock.authState.creds.registered) {
            setTimeout(async () => {
                try {
                    pairingCode = await sock.requestPairingCode(TARGET_PHONE);
                    console.log('\n======================================================');
                    console.log('🔢 WHATSAPP PAIRING CODE: ' + pairingCode);
                    console.log('Open WhatsApp > Linked Devices > Link with phone number');
                    console.log('======================================================\n');
                    fs.writeFileSync(path.join(__dirname, 'pairing_code.txt'), pairingCode);
                } catch (e) {
                    console.error('Pairing code request error:', e.message);
                }
            }, 3000);
        }

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                currentQR = qr;
                try {
                    await QRCode.toFile(path.join(__dirname, 'qr.png'), qr, { width: 400 });
                } catch (e) {}
            }
            if (connection === 'close') {
                isConnected = false;
                const statusCode = lastDisconnect && lastDisconnect.error && lastDisconnect.error.output ? lastDisconnect.error.output.statusCode : 0;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
                console.log('Connection closed (code: ' + statusCode + '). Reconnecting: ' + shouldReconnect);
                if (shouldReconnect) {
                    setTimeout(connectToWhatsApp, 3000);
                } else {
                    console.log('Logged out. Clearing auth and resetting...');
                    fs.rmSync(authFolder, { recursive: true, force: true });
                    setTimeout(connectToWhatsApp, 3000);
                }
            } else if (connection === 'open') {
                isConnected = true;
                currentQR = null;
                pairingCode = null;
                console.log('\n======================================================');
                console.log('✅ WHATSAPP CONNECTED SUCCESSFULLY & READY TO SEND ALERTS!');
                console.log('======================================================\n');
            }
        });

        sock.ev.on('creds.update', saveCreds);
    } catch (err) {
        console.error('Fatal socket error:', err);
        setTimeout(connectToWhatsApp, 5000);
    }
}

app.post('/send', async (req, res) => {
    try {
        const { number, message } = req.body;
        if (!sock || !isConnected) {
            return res.status(503).json({ success: false, error: 'WhatsApp is not connected yet.' });
        }
        let cleanNumber = String(number || TARGET_PHONE).replace(/[^0-9]/g, '');
        if (!cleanNumber.startsWith('91') && cleanNumber.length === 10) {
            cleanNumber = '91' + cleanNumber;
        }
        const jid = cleanNumber + '@s.whatsapp.net';
        await sock.sendMessage(jid, { text: message });
        console.log('[ALERT SENT] -> ' + jid);
        return res.json({ success: true, jid: jid });
    } catch (err) {
        console.error('Failed to send WhatsApp message:', err);
        return res.status(500).json({ success: false, error: err.message });
    }
});

app.get('/status', (req, res) => {
    res.json({
        connected: isConnected,
        pairing_code: pairingCode,
        has_qr: !!currentQR
    });
});

connectToWhatsApp();

app.listen(5001, '127.0.0.1', () => {
    console.log('WhatsApp Alert Gateway running on http://127.0.0.1:5001');
});
