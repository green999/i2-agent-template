# Company CA certificates

Put the public certificate(s) of the company's TLS-inspecting proxy here (for example `corporate-ca.pem`).
The Dockerfile adds every `*.crt` and `*.pem` in this folder to the container's trust store.

- Public certificates only. Never a private key, never a secret.
- Laptop: Python does not use the Windows certificate store. Build one bundle with the public roots plus the
  company certificate and point both variables at it in `.env.local`:
  `REQUESTS_CA_BUNDLE=certs/ca-bundle-local.pem` and `SSL_CERT_FILE=certs/ca-bundle-local.pem`.
  (`python -c "import certifi; print(certifi.where())"` shows the public bundle to start from.)
- Never switch certificate checks off in code. `ALLOW_INSECURE_TLS=true` exists for a one-off laptop test and is
  refused in Azure.
