# 🔐 Porkbun Certificate Sync

A Docker container with a web-based management interface for retrieving SSL certificates from Porkbun and hosting them in a mounted volume.

## Features

- 🌐 **Web Interface**: Easy-to-use web UI for managing certificates
- 🔑 **API Configuration**: Securely store and manage Porkbun API credentials
- 📦 **Domain Management**: Add and remove domains for certificate retrieval
- 📝 **Custom Naming**: Define custom naming structures for certificate files
- 🔄 **Format Conversion**: Support for multiple certificate formats (PEM, CRT, KEY, PFX/PKCS12)
- ⏰ **Scheduled Sync**: Automatic certificate synchronization on a schedule
- 💾 **YAML Configuration**: All settings stored in a YAML configuration file
- 🐳 **Docker Ready**: Fully containerized with Docker Compose support

## Quick Start

### Using Docker Compose

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  porkbun-cert-sync:
    image: ghcr.io/loryanstrant/porkbun-certificate-sync:latest
    container_name: porkbun-cert-sync
    ports:
      - "5000:5000"
    volumes:
      - ./certificates:/app/certificates
      - ./config:/app/config
    environment:
      - CONFIG_PATH=/app/config/config.yaml
    restart: unless-stopped
```

2. Start the container:

```bash
docker-compose up -d
```

3. Access the web interface at `http://localhost:5000`

### Using Docker CLI

```bash
docker run -d \
  --name porkbun-cert-sync \
  -p 5000:5000 \
  -v $(pwd)/certificates:/app/certificates \
  -v $(pwd)/config:/app/config \
  -e CONFIG_PATH=/app/config/config.yaml \
  ghcr.io/loryanstrant/porkbun-certificate-sync:latest
```

## Configuration

### Web Interface

Access the web interface at `http://localhost:5000` to configure:

1. **API Settings**: Enter your Porkbun API key and secret key
2. **Domains**: Add domains to retrieve certificates for
3. **Certificate Settings**: 
   - Output directory
   - File naming format (use `{domain}` placeholder)
   - Certificate formats (PEM, CRT, KEY, PFX)
4. **Schedule**: Configure automatic sync schedule using cron format

### YAML Configuration

The configuration is stored in `/app/config/config.yaml`:

```yaml
api:
  api_key: "your-api-key"
  secret_key: "your-secret-key"

domains:
  - domain: "example.com"
    custom_name: "example"
    alt_names: []

certificates:
  output_dir: "/app/certificates"
  naming_format: "{domain}"
  formats:
    - pem
    - crt
    - key

schedule:
  enabled: true
  cron: "0 2 * * *"  # 2 AM daily
```

## Certificate Formats

- **PEM**: Full chain, private key, and certificate as separate files
- **CRT**: Certificate chain as a single `.crt` file
- **KEY**: Private key as a separate `.key` file
- **PFX/PKCS12**: Combined certificate and private key in `.pfx` format

## API Endpoints

The application provides a REST API:

- `GET /api/settings` - Get current settings
- `POST /api/settings/api` - Update API credentials
- `POST /api/settings/certificates` - Update certificate settings
- `POST /api/settings/schedule` - Update schedule settings
- `GET /api/domains` - List configured domains
- `POST /api/domains` - Add a new domain
- `DELETE /api/domains/<domain>` - Remove a domain
- `POST /api/sync` - Manually trigger certificate sync
- `GET /api/sync/status` - Get sync status
- `GET /health` - Health check endpoint

## Building from Source

```bash
# Clone the repository
git clone https://github.com/loryanstrant/Porkbun-Certificate-Sync.git
cd Porkbun-Certificate-Sync

# Build the Docker image
docker build -t porkbun-cert-sync .

# Run the container
docker-compose up -d
```

## Development

### Requirements

- Python 3.11+
- Docker
- Docker Compose

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export CONFIG_PATH=./config/config.yaml

# Run the application
python -m flask --app app.main run --host 0.0.0.0 --port 5000
```

## Environment Variables

- `CONFIG_PATH`: Path to configuration file (default: `/app/config/config.yaml`)
- `SECRET_KEY`: Flask secret key for session management
- `FLASK_APP`: Flask application module (default: `app.main`)

## Volumes

- `/app/certificates`: Certificate storage directory
- `/app/config`: Configuration file directory

## Ports

- `5000`: Web interface and API

## Security Notes

- Store your Porkbun API credentials securely
- Use HTTPS in production environments
- Restrict access to the web interface using a reverse proxy
- Regularly update certificates and rotate credentials
- The container runs as root by default; consider using a non-root user in production

## Troubleshooting

### API Connection Issues

Check your API credentials in the Settings tab. Use the "Test Connection" feature to verify.

### Certificate Sync Failures

- Ensure the domain is configured in Porkbun
- Verify API credentials have the correct permissions
- Check container logs: `docker logs porkbun-cert-sync`

### Permission Issues

Ensure the mounted volumes have appropriate permissions:

```bash
chmod 755 certificates config
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Porkbun](https://porkbun.com/) for their API
- [Flask](https://flask.palletsprojects.com/) web framework
- [APScheduler](https://apscheduler.readthedocs.io/) for scheduling
