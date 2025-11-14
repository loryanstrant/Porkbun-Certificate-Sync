# 🔐 Porkbun Certificate Sync

A Docker container with a web-based management interface for retrieving SSL certificates from Porkbun and hosting them in a mounted volume.

## Features

- 🌐 **Web Interface**: Easy-to-use web UI for managing certificates
- 🔑 **API Configuration**: Securely store and manage Porkbun API credentials
- 📦 **Domain Management**: Add, edit, and remove domains for certificate retrieval
- 📝 **Custom Naming**: Define custom naming structures for certificate files with multiple options
  - Custom base names for certificates
  - Configurable file name separators (underscore, hyphen, dot)
  - Alternative file name variants for flexibility
- 🔄 **Format Conversion**: Support for multiple certificate formats (PEM, CRT, KEY, PFX/PKCS12)
- 🚀 **SSH Distribution**: Automatically distribute certificates to remote servers via SSH
  - Configure multiple remote hosts with friendly display names
  - Secure password storage with encryption
  - Automatic distribution after successful certificate sync
  - Sudo support for deploying to protected directories
  - Specify custom certificate paths on remote servers
  - Collapsible host cards for clean interface
  - Alphabetically sorted host list
- 📋 **Distribution Logging**: Comprehensive logging of all sync and distribution events
  - Track certificate sync events
  - Monitor distribution success/failure per host
  - Filter logs by event type
  - View statistics dashboard
- ⏰ **Human-Friendly Scheduling**: Intuitive schedule configuration with:
  - Easy-to-use frequency selectors (Hourly, Daily, Weekly, Specific Days, Monthly)
  - Visual time pickers for hour and minute selection
  - Real-time cron expression preview
- 🌓 **Dark Mode**: Toggle between light and dark themes for comfortable viewing
- 💾 **YAML Configuration**: All settings stored in a YAML configuration file
- 🐳 **Docker Ready**: Fully containerized with Docker Compose support

## Screenshots

### Light Mode
<img src="https://github.com/user-attachments/assets/74143c1c-bcde-4e37-b573-497b92912579" alt="Settings Tab - Light Mode" width="800">

*Settings tab showing API configuration, certificate settings, and the intuitive schedule configuration interface*

<img src="https://github.com/user-attachments/assets/291fce27-4db9-469f-9ffb-3ba2390fee86" alt="Domains Tab - Light Mode" width="800">

*Domains tab with enhanced domain management features including custom naming and file separators*

<img src="https://github.com/user-attachments/assets/ce7365eb-3165-4241-b0dc-288bc0c6728c" alt="Distribution Tab - Light Mode" width="800">

*Distribution tab for configuring SSH hosts where certificates will be automatically distributed*

<img src="https://github.com/user-attachments/assets/6433b710-5a25-4c9f-86e2-a1c1be465ec6" alt="Distribution Expanded - Light Mode" width="800">

*Expanded view of a configured SSH host showing all connection details*

<img src="https://github.com/user-attachments/assets/ed0fce32-4a09-4305-b442-3a92f543abab" alt="Logs Tab - Light Mode" width="800">

*Logs tab displaying distribution events, statistics, and filtering options*

### Dark Mode
<img src="https://github.com/user-attachments/assets/37c28b18-d8d1-4da1-bd1d-d3a84d3dabc0" alt="Settings Tab - Dark Mode" width="800">

*Dark mode provides a comfortable viewing experience in low-light environments*

<img src="https://github.com/user-attachments/assets/5fb89d36-64f8-4369-9d07-7de30083e822" alt="Domains Tab - Dark Mode" width="800">

*Domain management interface in dark mode*

<img src="https://github.com/user-attachments/assets/6c6ff9b7-cd67-4910-928f-d72d7332c7da" alt="Logs Tab - Dark Mode" width="800">

*Distribution logs with statistics in dark mode*

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
2. **Domains**: Add and edit domains to retrieve certificates for
   - Set custom base names for certificate files
   - Choose file name separators (underscore, hyphen, or dot)
   - Define alternative file name variants
   - Edit existing domain configurations
3. **Distribution**: Configure SSH hosts for automatic certificate distribution
   - Add multiple remote hosts with friendly display names
   - Specify hostname/IP address, port, username, and password
   - Set the remote certificate path
   - Edit or delete existing hosts
   - Hosts are displayed in collapsible cards sorted alphabetically
4. **Logs**: View distribution and sync event logs
   - See statistics for total syncs, distributions, successes, and failures
   - Filter logs by event type
   - Review detailed information for each event
5. **Certificate Settings**: 
   - Output directory
   - File naming format (use `{domain}` placeholder)
   - Certificate formats (PEM, CRT, KEY, PFX)
6. **Schedule**: Configure automatic sync schedule with user-friendly options
   - Select frequency: Hourly, Daily, Weekly, Specific Days, or Monthly
   - Choose specific time with dropdown menus
   - Preview the generated cron expression in real-time
7. **Theme**: Toggle between light and dark mode using the theme button in the header

### YAML Configuration

The configuration is stored in `/app/config/config.yaml`:

```yaml
api:
  api_key: "your-api-key"
  secret_key: "your-secret-key"

domains:
  - domain: "example.com"
    custom_name: "example"  # Optional: custom base name for certificate files
    separator: "_"  # File name separator: "_", "-", or "."
    alt_names: []  # Optional: alternative file name variants

certificates:
  output_dir: "/app/certificates"
  naming_format: "{domain}"
  formats:
    - pem
    - crt
    - key

ssh_hosts:
  - display_name: "Production Server"
    hostname: "prod.example.com"
    port: 22
    username: "root"
    password_encrypted: "encrypted_password_here"  # Password is securely encrypted
    cert_path: "/etc/ssl/certs"
    use_sudo: true  # Use sudo for privileged operations
  - display_name: "Staging Server"
    hostname: "staging.example.com"
    port: 22
    username: "deploy"
    password_encrypted: "encrypted_password_here"
    cert_path: "/opt/certificates"
    use_sudo: false  # No sudo required

schedule:
  enabled: true
  cron: "0 2 * * *"  # 2 AM daily (configured via user-friendly UI)
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
- `PUT /api/domains/<domain>` - Update an existing domain
- `DELETE /api/domains/<domain>` - Remove a domain
- `GET /api/ssh-hosts` - List configured SSH hosts
- `POST /api/ssh-hosts` - Add a new SSH host
- `PUT /api/ssh-hosts/<display_name>` - Update an existing SSH host
- `DELETE /api/ssh-hosts/<display_name>` - Remove an SSH host
- `POST /api/distribution/test` - Test SSH connection to a host
- `GET /api/distribution/logs` - Get distribution logs
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
- `ENCRYPTION_KEY`: (Optional) Encryption key for SSH passwords. If not set, a key is automatically generated and saved to `/app/config/.encryption_key`, which persists across container restarts as long as the config volume is mounted. You can manually set this if you need to use the same key across multiple instances. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

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
- **Important**: PFX/PKCS12 files are created without password protection by default for compatibility. Ensure the certificate directory has appropriate file permissions (e.g., `chmod 700 certificates`) to protect private keys
- Set the `SECRET_KEY` environment variable for production deployments to maintain session persistence

### SSH Distribution Security

- **Password Storage**: SSH passwords are encrypted using Fernet symmetric encryption before storage in the configuration file. The encryption key is automatically generated and persisted to `/app/config/.encryption_key` (which is in the mounted config volume), ensuring passwords remain valid across container updates and restarts. Alternatively, you can manually set the `ENCRYPTION_KEY` environment variable if you need to use the same key across multiple instances.
- **Sudo Support**: The application supports using `sudo` for privileged operations when deploying certificates to protected directories. This is useful when certificates need to be placed in system directories like `/etc/ssl/certs`.
- **Automatic Distribution**: After successful certificate sync, certificates are automatically distributed to all configured SSH hosts. This eliminates the need for manual copying and ensures all servers have the latest certificates.
- **SSH Key Alternative**: For enhanced security, consider using SSH key-based authentication instead of passwords (future enhancement)
- **Host Key Validation**: The application uses `AutoAddPolicy` to automatically accept SSH host keys for ease of deployment. This accepts unknown host keys without validation, which could be susceptible to man-in-the-middle attacks. For production use, consider implementing SSH key-based authentication with proper known_hosts validation
- **Network Security**: Ensure SSH access is properly secured on target servers (firewall rules, fail2ban, etc.)
- **Least Privilege**: Use dedicated service accounts with minimal permissions on remote servers. Enable `use_sudo` only when necessary.
- **Audit Logs**: Review distribution logs regularly to monitor certificate deployment activities
- **Secure Transmission**: SSH connections use standard SSH protocol encryption for secure file transfer

## Troubleshooting

### API Connection Issues

Check your API credentials in the Settings tab. Use the "Test Connection" feature to verify.

### Certificate Sync Failures

- Ensure the domain is configured in Porkbun
- Verify API credentials have the correct permissions
- Check container logs: `docker logs porkbun-cert-sync`

### Permission Issues

#### Local File System

Ensure the mounted volumes have appropriate permissions:

```bash
chmod 755 certificates config
```

#### SSH Distribution

If you encounter "Permission denied" errors when distributing certificates to remote hosts:

1. Check the error message in the distribution logs
2. If the remote path requires elevated privileges (e.g., `/etc/ssl/certs`), enable `use_sudo: true` in your SSH host configuration
3. Ensure the remote user account has sudo privileges
4. Verify the remote user's password is correctly configured

Example configuration for hosts requiring sudo:

```yaml
ssh_hosts:
  - display_name: "My Server"
    hostname: "server.example.com"
    port: 22
    username: "deploy"
    password_encrypted: "..."
    cert_path: "/etc/ssl/certs"
    use_sudo: true  # Enable this for paths requiring elevated privileges
```


## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## Development Approach
<img width="256" height="256" alt="Vibe Coding with GitHub Copilot 256x256" src="https://github.com/user-attachments/assets/bb41d075-6b3e-4f2b-a88e-94b2022b5d4f" />


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Porkbun](https://porkbun.com/) for their API
- [Flask](https://flask.palletsprojects.com/) web framework
- [APScheduler](https://apscheduler.readthedocs.io/) for scheduling
