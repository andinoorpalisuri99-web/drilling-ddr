/* Precache only the public application shell. Authenticated API data stays out of Cache Storage. */
const CACHE='mms-drilling-shell-v0.8.20';
const SHELL=['/','/index.html','/app.css','/workspace-layout.css','/layout.js','/drilling-map.js','/drilling-map.css','/leaflet.js','/leaflet.css','/app.js','/offline.js','/ddr-form.js','/pdf.min.mjs','/pdf.worker.min.mjs','/modules.js','/enhancements.js','/scanner.js','/navigation.js','/rigs.js','/workspace.js','/analytics.js','/label.js','/mms-logo.png','/login-background.webp'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('mms-drilling-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{const request=event.request;if(request.method!=='GET'||new URL(request.url).pathname.startsWith('/api/'))return;
 const url=new URL(request.url);if(url.origin!==self.location.origin)return;
 if(request.mode==='navigate'){event.respondWith(fetch(request).catch(()=>caches.match('/index.html')));return}
 if(SHELL.includes(url.pathname))event.respondWith(caches.match(request).then(hit=>hit||fetch(request)));
});
