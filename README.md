# l2p - Local to Public

## Installation
```
pip install local2public
```

## Usage
```
ltp --port [port_number] --name [your_website_name]
```

The public URL is generated as a subdomain:
```
https://[your_website_name].techmentor.uz/
```

For deployment, point `*.techmentor.uz` to the server and set:
```
LTP_BASE_DOMAIN=techmentor.uz
```

For the CLI, set:
```
LTP_SERVER_URL=wss://techmentor.uz/tunnel
LTP_PUBLIC_BASE_URL=https://techmentor.uz
```

## Production notes
For Azure with Caddy:

- Create DNS records for both `techmentor.uz` and `*.techmentor.uz` pointing to the Azure public IP.
- Open ports `80` and `443` in the Azure network security group so Caddy can issue and renew certificates.
- Run the FastAPI app behind Caddy, for example on `127.0.0.1:8000`.
- Use the included `Caddyfile.example` as the starting reverse proxy config.
- Keep FastAPI docs disabled in production. They are disabled by default; set `LTP_ENABLE_DOCS=true` only while debugging.

Recommended server environment:
```
LTP_BASE_DOMAIN=myurl.com
LTP_REQUEST_TIMEOUT=30
LTP_MAX_BODY_BYTES=10485760
```

# O'zbekchada
## O'RNATISH
```
pip install local2public
```

## ISHLATISH
```
ltp --port [port_raqami] --name [websaytingizning_nomi]
```

URL subdomain orqali yaratiladi:
```
https://[websaytingizning_nomi].techmentor.uz/
```
