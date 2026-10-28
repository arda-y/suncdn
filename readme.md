# sun

File upload API with a CDN and reverse proxy setup. Upload a file, get back a link.

## Setup

1. Edit `config.yaml` (see below) and `docker-compose.yml` volumes/port if needed.
2. Build and run:

```bash
sudo docker compose up -d --build
```

Config is baked into the image at build time (not bind-mounted), so any change to `config.yaml` needs a rebuild to take effect — use `rebuild.sh sun` (the container name), not a plain restart.

## Config (`config.yaml`)

| Setting | Description | Default |
| --- | --- | --- |
| `ROOT_PATH` | Reverse proxied path to the API | `/sun` |
| `CDN_PATH` | Reverse proxied path to the CDN | `/suncdn` |
| `PORT` | API server port | `2003` |
| `MAX_FILE_SIZE` | Max upload size in MB | `1536` |
| `IP_OR_DOMAIN` | Address used to build CDN links | `https://cdn.arda0.net` |
| `DELETE_BASE_URL` | Base URL for early-deletion links (must route `/delete/` to the API) | `https://cdn.arda0.net/sun` |
| `MAX_FILE_AGE` | File TTL in seconds before purge | `604800` |
| `LOG_LEVEL` | Log verbosity | `info` |
| `ALLOWED_DOMAINS` | CORS allowed origins | see `config.yaml` |

## Early deletion

`POST /uploadfile/` returns two links: `file_location` (the download) and `delete_location`.

- `GET <delete_location>` shows a confirm page. A GET never deletes, so link previews are harmless.
- `DELETE <delete_location>` deletes the upload. Wrong id, wrong token and already-deleted all return the same 404.
- Only a SHA-256 hash of each token is stored (`mountpoint/delete_tokens/<id>`, not served by nginx). The purge task removes token files of expired uploads.
- nginx must route `/sun/delete/` to the API on the CDN host (`cdn.arda0.net` is DNS-only, so scripts skip Cloudflare's bot challenge).
- The web page keeps the delete link in the browser's upload history and offers it as a DEL button.
