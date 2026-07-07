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
https://[your_website_name].myurl.com/
```

For deployment, point `*.myurl.com` to the server and set:
```
LTP_BASE_DOMAIN=myurl.com
```

For the CLI, set:
```
LTP_SERVER_URL=wss://myurl.com/tunnel
LTP_PUBLIC_BASE_URL=https://myurl.com
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
https://[websaytingizning_nomi].myurl.com/
```
