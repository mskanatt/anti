# Vendor: vosk-browser

Распознавание речи в браузере устройства использует `vosk-browser`
(WASM-порт Vosk). Добавьте файл сюда перед деплоем:

```bash
npm install vosk-browser
cp node_modules/vosk-browser/dist/vosk.js static/vendor/vosk.js
```

или скачайте UMD-сборку с CDN:
https://unpkg.com/vosk-browser/dist/vosk.js

`window.Vosk.createModel(url)` — единственная функция, которую использует
`device-listener.js`.