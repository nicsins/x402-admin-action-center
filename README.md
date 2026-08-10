# x402 Services Action Center

Deploy to Vercel and attach **admin.x402-micro-pay.com**.

## Environment variables
- `MARKETPLACE_URL=https://x402-micro-pay.com`
- `X402_GATEWAY_URL=https://x402-micro-pay.com`

## DNS (subdomain)
Add CNAME: `admin` → `cname.vercel-dns.com` (or the target Vercel shows when you add the domain).

## Local
```bash
pip install -r requirements.txt
uvicorn api.index:app --reload --port 8100
```
