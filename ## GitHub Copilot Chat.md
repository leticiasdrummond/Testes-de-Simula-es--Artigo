## GitHub Copilot Chat

- Extension: 0.44.1 (prod)
- VS Code: 1.116.0 (560a9dba96f961efea7b1612916f89e5d5d4d679)
- OS: win32 10.0.26200 x64
- GitHub Account: leticiasdrummond

## Network

User Settings:
```json
  "http.systemCertificatesNode": true,
  "github.copilot.advanced.debug.useElectronFetcher": true,
  "github.copilot.advanced.debug.useNodeFetcher": false,
  "github.copilot.advanced.debug.useNodeFetchFetcher": true
```

Connecting to https://api.github.com:
- DNS ipv4 Lookup: Error (0 ms): getaddrinfo ENOTFOUND api.github.com
- DNS ipv6 Lookup: Error (1 ms): getaddrinfo ENOTFOUND api.github.com
- Proxy URL: None (1 ms)
- Electron fetch (configured): timed out after 10 seconds
- Node.js https: timed out after 10 seconds
- Node.js fetch: Error (13 ms): TypeError: fetch failed
	at node:internal/deps/undici/undici:14902:13
	at process.processTicksAndRejections (node:internal/process/task_queues:103:5)
	at async t._fetch (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5298:5229)
	at async t.fetch (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5298:4541)
	at async u (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5330:186)
	at async xg._executeContributedCommand (file:///c:/Users/letic/AppData/Local/Programs/Microsoft%20VS%20Code/560a9dba96/resources/app/out/vs/workbench/api/node/extensionHostProcess.js:501:48675)
  Error: getaddrinfo ENOTFOUND api.github.com
  	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
  	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)

Connecting to https://api.githubcopilot.com/_ping:
- DNS ipv4 Lookup: Error (0 ms): getaddrinfo ENOTFOUND api.githubcopilot.com
- DNS ipv6 Lookup: Error (2 ms): getaddrinfo ENOTFOUND api.githubcopilot.com
- Proxy URL: None (2 ms)
- Electron fetch (configured): timed out after 10 seconds
- Node.js https: timed out after 10 seconds
- Node.js fetch: Error (1059 ms): TypeError: fetch failed
	at node:internal/deps/undici/undici:14902:13
	at process.processTicksAndRejections (node:internal/process/task_queues:103:5)
	at async t._fetch (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5298:5229)
	at async t.fetch (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5298:4541)
	at async u (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5330:186)
	at async xg._executeContributedCommand (file:///c:/Users/letic/AppData/Local/Programs/Microsoft%20VS%20Code/560a9dba96/resources/app/out/vs/workbench/api/node/extensionHostProcess.js:501:48675)
  Error: getaddrinfo ENOTFOUND api.githubcopilot.com
  	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
  	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)

Connecting to https://copilot-proxy.githubusercontent.com/_ping:
- DNS ipv4 Lookup: Error (1 ms): getaddrinfo ENOTFOUND copilot-proxy.githubusercontent.com
- DNS ipv6 Lookup: Error (1 ms): getaddrinfo ENOTFOUND copilot-proxy.githubusercontent.com
- Proxy URL: None (2 ms)
- Electron fetch (configured): timed out after 10 seconds
- Node.js https: Error (7 ms): Error: getaddrinfo ENOTFOUND copilot-proxy.githubusercontent.com
	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)
- Node.js fetch: Error (13 ms): TypeError: fetch failed
	at node:internal/deps/undici/undici:14902:13
	at process.processTicksAndRejections (node:internal/process/task_queues:103:5)
	at async t._fetch (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5298:5229)
	at async t.fetch (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5298:4541)
	at async u (c:\Users\letic\.vscode\extensions\github.copilot-chat-0.44.1\dist\extension.js:5330:186)
	at async xg._executeContributedCommand (file:///c:/Users/letic/AppData/Local/Programs/Microsoft%20VS%20Code/560a9dba96/resources/app/out/vs/workbench/api/node/extensionHostProcess.js:501:48675)
  Error: getaddrinfo ENOTFOUND copilot-proxy.githubusercontent.com
  	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
  	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)

Connecting to https://mobile.events.data.microsoft.com: Error (7941 ms): Error: net::ERR_NAME_NOT_RESOLVED
	at SimpleURLLoaderWrapper.<anonymous> (node:electron/js2c/utility_init:2:10684)
	at SimpleURLLoaderWrapper.emit (node:events:519:28)
	at SimpleURLLoaderWrapper.callbackTrampoline (node:internal/async_hooks:130:17)
  {"is_request_error":true,"network_process_crashed":false}
Connecting to https://dc.services.visualstudio.com: timed out after 10 seconds
Connecting to https://copilot-telemetry.githubusercontent.com/_ping: Error (6 ms): Error: getaddrinfo ENOTFOUND copilot-telemetry.githubusercontent.com
	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)
Connecting to https://copilot-telemetry.githubusercontent.com/_ping: Error (6 ms): Error: getaddrinfo ENOTFOUND copilot-telemetry.githubusercontent.com
	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)
Connecting to https://default.exp-tas.com: Error (7 ms): Error: getaddrinfo ENOTFOUND default.exp-tas.com
	at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:122:26)
	at GetAddrInfoReqWrap.callbackTrampoline (node:internal/async_hooks:130:17)

Number of system certificates: 75

## Documentation

In corporate networks: [Troubleshooting firewall settings for GitHub Copilot](https://docs.github.com/en/copilot/troubleshooting-github-copilot/troubleshooting-firewall-settings-for-github-copilot).