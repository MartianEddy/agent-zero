# Render object storage with Cloudflare R2

The Render Blueprint expects an S3-compatible bucket. For the current MVP setup, use a dedicated private Cloudflare R2 bucket and bucket-scoped S3 credentials.

## Cloudflare setup

1. In Cloudflare, open **R2 Object Storage** and create a dedicated bucket, for example `agent-zero-media`. Keep it private: do not enable `r2.dev` public access or attach a public custom domain.
2. Under **Manage R2 API Tokens**, create a token with **Object Read & Write**, scoped to this bucket only. Copy the S3 **Access Key ID** and **Secret Access Key** when shown; the secret is only shown once.
3. Copy the S3 endpoint for the account: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

R2 uses region `auto`, which is already set in `render.yaml`. The SDK uses HTTPS when `OBJECT_STORAGE_SECURE=true`. Cloudflare encrypts R2 objects at rest; Agent 0 does not send an S3 `ServerSideEncryption` request header because R2 does not support that header.

## Render environment variables

Set the following on **both** `agent-zero-api` and `agent-zero-worker`:

| Variable | Value |
| --- | --- |
| `OBJECT_STORAGE_ENDPOINT` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `OBJECT_STORAGE_BUCKET` | Exact bucket name created above |
| `OBJECT_STORAGE_ACCESS_KEY` | R2 S3 Access Key ID |
| `OBJECT_STORAGE_SECRET_KEY` | R2 S3 Secret Access Key |
| `OBJECT_STORAGE_REGION` | `auto` |
| `OBJECT_STORAGE_SECURE` | `true` |

Save the variables and let each service redeploy. Once both are running, `GET /api/v1/ready` should report `object_storage: ok`; the endpoint also requires PostgreSQL and Redis to pass. Do not test upload with real or sensitive media until the access-control and retention decisions are resolved.

## Recovery

If credentials are exposed, revoke the R2 API token and create a new bucket-scoped token, then update both Render services. If the bucket name or endpoint is wrong, correct the Render variables and redeploy. Keep the bucket private; application previews are served through Agent 0's owner-scoped API rather than directly from R2.
