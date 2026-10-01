#!/bin/sh
# Proves the network design (CLAUDE.md): no container has general internet; only the gateway reaches Ollama.
fail=0
check() { # description, expected (blocked|open), command...
  desc="$1"; want="$2"; shift 2
  if "$@" >/dev/null 2>&1; then got=open; else got=blocked; fi
  if [ "$got" = "$want" ]; then echo "  ok   $desc ($got)"; else echo "  FAIL $desc (expected $want, got $got)"; fail=1; fi
}
echo "Network isolation check"
check "api cannot reach the internet"          blocked docker compose exec -T api python -c "import urllib.request;urllib.request.urlopen('https://example.com',timeout=4)"
check "worker cannot reach the internet"       blocked docker compose exec -T worker python -c "import urllib.request;urllib.request.urlopen('https://example.com',timeout=4)"
check "worker cannot reach Ollama"             blocked docker compose exec -T worker python -c "import socket;socket.create_connection(('ollama.internal',11434),timeout=3)"
check "worker cannot reach Gmail's send API"   blocked docker compose exec -T worker python -c "import urllib.request;urllib.request.urlopen('https://gmail.googleapis.com/',timeout=4)"
check "api cannot reach Gmail's send API"      blocked docker compose exec -T api python -c "import urllib.request;urllib.request.urlopen('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',timeout=4)"
check "api can reach Ollama (the gateway)"     open    docker compose exec -T api python -c "import urllib.request;urllib.request.urlopen('http://ollama.internal:11434/api/version',timeout=6)"
check "ui can reach the api"                   open    docker compose exec -T ui node -e "fetch('http://api:8000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
[ $fail -eq 0 ] && echo "All network checks passed." || { echo "A network check FAILED."; exit 1; }
